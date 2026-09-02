"""
Selector automático de modelo IA para rembg.
Analiza heurísticas de la imagen (paleta, proporciones, saturación, complejidad de bordes)
para elegir el modelo de remoción de fondo más adecuado sin intervención manual.
"""

import logging
from collections import Counter
from dataclasses import dataclass
from typing import Tuple

from PIL import Image, ImageFilter, ImageStat

logger = logging.getLogger(__name__)


MODEL_CATALOG = {
    "bria-rmbg": {
        "description": "SOTA RMBG-1.4 – Máxima precisión en bordes, retratos y sombras",
        "speed": "muy rápida",
        "precision": "extrema",
    },
    "birefnet-general": {
        "description": "BiRefNet – Segmentación bilateral ultra nítida de alta resolución",
        "speed": "media",
        "precision": "extrema",
    },
    "u2net": {
        "description": "General – personas, objetos cotidianos",
        "speed": "media",
        "precision": "alta",
    },
    "u2net_human_seg": {
        "description": "Retratos / personas en primer plano",
        "speed": "rápida",
        "precision": "muy alta en humanos",
    },
    "isnet-general-use": {
        "description": "Objetos complejos y productos comerciales",
        "speed": "lenta",
        "precision": "muy alta",
    },
    "silueta": {
        "description": "Siluetas simples y fondos claros muy uniformes",
        "speed": "muy rápida",
        "precision": "media",
    },
}


@dataclass
class ModelSelectionResult:
    model_name: str
    reason: str
    confidence: float
    metrics: dict


class ModelSelector:
    BG_UNIFORMITY_THRESHOLD = 0.85
    PORTRAIT_ASPECT_MIN = 1.20
    PORTRAIT_ASPECT_MAX = 3.50
    SKIN_HUE_MIN = 5
    SKIN_HUE_MAX = 35
    SKIN_SAT_MIN = 0.20
    SKIN_PIXEL_RATIO = 0.10
    ANIME_SAT_THRESHOLD = 0.55
    ANIME_COLOR_RANGE = 40
    EDGE_COMPLEXITY_HIGH = 0.18
    # Fondo oscuro: brillo medio < 35% → silueta no es suficiente para fondos oscuros
    DARK_BG_BRIGHTNESS = 0.35
    # Fondo cromatico (no gris): saturacion del borde > 10% → indica ilustración
    CHROMATIC_BG_SAT = 0.10

    def select(self, image: Image.Image) -> ModelSelectionResult:
        analysis_img = self._prepare(image)
        metrics = self._compute_metrics(analysis_img)
        model, reason, confidence = self._decide(metrics)
        logger.info(
            f"[ModelSelector] Modelo seleccionado: '{model}' | Razon: {reason} | Confianza: {confidence:.0%}"
        )
        return ModelSelectionResult(model_name=model, reason=reason, confidence=confidence, metrics=metrics)

    def _prepare(self, image: Image.Image) -> Image.Image:
        img = image.convert("RGB")
        max_dim = 256
        ratio = min(max_dim / img.width, max_dim / img.height)
        if ratio < 1.0:
            new_size = (int(img.width * ratio), int(img.height * ratio))
            img = img.resize(new_size, Image.BILINEAR)
        return img

    def _compute_metrics(self, img: Image.Image) -> dict:
        w, h = img.size
        pixels = list(img.getdata())
        total = len(pixels)

        border_pixels = self._get_border_pixels(img)
        bg_uniformity = self._color_uniformity(border_pixels)
        aspect_ratio = h / w

        hsv_pixels = [self._rgb_to_hsv(r, g, b) for r, g, b in pixels]
        hues = [hsv[0] for hsv in hsv_pixels]
        sats = [hsv[1] for hsv in hsv_pixels]

        mean_saturation = sum(sats) / total
        chromatic_hues = [hu for hu, s in zip(hues, sats) if s > 0.15]
        hue_range = (max(chromatic_hues) - min(chromatic_hues)) if len(chromatic_hues) > 10 else 360

        skin_count = sum(
            1 for hu, s, v in hsv_pixels
            if self.SKIN_HUE_MIN <= hu <= self.SKIN_HUE_MAX and s >= self.SKIN_SAT_MIN and v >= 0.30
        )
        skin_ratio = skin_count / total

        gray = img.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edges)
        edge_complexity = edge_stat.mean[0] / 255.0

        # Brillo medio del borde (para detectar fondos oscuros tipo ilustración)
        border_hsv = [self._rgb_to_hsv(r, g, b) for r, g, b in border_pixels]
        mean_bg_brightness = sum(v for _, _, v in border_hsv) / max(len(border_hsv), 1)
        mean_bg_saturation = sum(s for _, s, _ in border_hsv) / max(len(border_hsv), 1)

        return {
            "bg_uniformity": round(bg_uniformity, 4),
            "aspect_ratio": round(aspect_ratio, 4),
            "mean_saturation": round(mean_saturation, 4),
            "hue_range": round(hue_range, 2),
            "skin_ratio": round(skin_ratio, 4),
            "edge_complexity": round(edge_complexity, 4),
            "mean_bg_brightness": round(mean_bg_brightness, 4),
            "mean_bg_saturation": round(mean_bg_saturation, 4),
            "width": w,
            "height": h,
        }

    def _decide(self, m: dict) -> Tuple[str, str, float]:
        # 1. Fondo uniforme detectado -- verificar si es oscuro o cromático
        if m["bg_uniformity"] >= self.BG_UNIFORMITY_THRESHOLD:
            is_dark_bg = m.get("mean_bg_brightness", 1.0) < self.DARK_BG_BRIGHTNESS
            is_chromatic_bg = m.get("mean_bg_saturation", 0.0) > self.CHROMATIC_BG_SAT

            if is_dark_bg or is_chromatic_bg:
                # Fondo oscuro o con color (ej: azul oscuro, teal, negro)
                # bria-rmbg elimina el 100% de las sombras y bruma en fondos oscuros
                reason = (
                    f"Fondo uniforme pero oscuro/cromático "
                    f"(brillo={m.get('mean_bg_brightness',0):.0%}, sat={m.get('mean_bg_saturation',0):.0%}): "
                    f"usando SOTA RMBG (bria-rmbg) para eliminar sombras"
                )
                return ("bria-rmbg", reason, 0.95)

            # Fondo claro y uniforme (blanco, gris claro, beige)
            return (
                "silueta",
                f"Fondo claro y uniforme ({m['bg_uniformity']:.0%} del borde homogéneo)",
                m["bg_uniformity"],
            )

        # 2. Retratos / personas / figuras humanas
        is_portrait = self.PORTRAIT_ASPECT_MIN <= m["aspect_ratio"] <= self.PORTRAIT_ASPECT_MAX
        has_skin = m["skin_ratio"] >= self.SKIN_PIXEL_RATIO
        if is_portrait or has_skin:
            confidence = min(1.0, max(0.85, (m["skin_ratio"] / 0.25)))
            return (
                "bria-rmbg",
                f"Figura/Retrato detectado (proporción {m['aspect_ratio']:.2f}, piel {m['skin_ratio']:.0%}): "
                f"usando SOTA RMBG para máxima nitidez en bordes y manos",
                confidence,
            )

        # 3. Arte / ilustración / saturación marcada
        is_high_sat = m["mean_saturation"] >= self.ANIME_SAT_THRESHOLD
        if is_high_sat:
            return (
                "bria-rmbg",
                f"Ilustración/Arte de alto contraste (saturación {m['mean_saturation']:.0%}): "
                f"usando SOTA RMBG",
                0.90,
            )

        # 4. Objeto complejo de alta densidad de bordes
        if m["edge_complexity"] >= self.EDGE_COMPLEXITY_HIGH:
            return (
                "birefnet-general",
                f"Objeto/producto de alta complejidad (densidad de bordes {m['edge_complexity']:.0%}): "
                f"usando BiRefNet",
                0.90,
            )

        # 5. Fallback por defecto: SOTA RMBG para máxima calidad
        return ("bria-rmbg", "Propósito general: usando SOTA RMBG (bria-rmbg) para máxima fidelidad", 0.85)

    def _get_border_pixels(self, img: Image.Image):
        w, h = img.size
        pixels = []
        for x in range(w):
            pixels.append(img.getpixel((x, 0)))
            pixels.append(img.getpixel((x, h - 1)))
        for y in range(1, h - 1):
            pixels.append(img.getpixel((0, y)))
            pixels.append(img.getpixel((w - 1, y)))
        return pixels

    def _color_uniformity(self, pixels) -> float:
        if not pixels:
            return 0.0
        quantized = [(r >> 5, g >> 5, b >> 5) for r, g, b in pixels]
        most_common_count = Counter(quantized).most_common(1)[0][1]
        return most_common_count / len(pixels)

    @staticmethod
    def _rgb_to_hsv(r: int, g: int, b: int) -> Tuple[float, float, float]:
        r, g, b = r / 255.0, g / 255.0, b / 255.0
        max_c = max(r, g, b)
        min_c = min(r, g, b)
        delta = max_c - min_c
        v = max_c
        s = (delta / max_c) if max_c != 0 else 0.0
        if delta == 0:
            h = 0.0
        elif max_c == r:
            h = 60.0 * (((g - b) / delta) % 6)
        elif max_c == g:
            h = 60.0 * (((b - r) / delta) + 2)
        else:
            h = 60.0 * (((r - g) / delta) + 4)
        return h, s, v
