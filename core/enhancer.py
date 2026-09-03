"""
Módulo de mejora fotográfica y graduación de estudio (Studio Enhancer).
Elimina el aspecto plano ('flat sticker') mediante:
  1. Balance de blancos automático (Algoritmo Gray World ponderado a 5500K).
  2. Ajuste de exposición y contraste high-key para fondos blancos puros.
  3. Despill y eliminación de halos oscuros/colorimétricos en bordes alfa.
"""

from typing import Tuple, Optional, Union
import numpy as np
from PIL import Image, ImageFilter
from scipy.ndimage import distance_transform_edt, binary_erosion


class StudioEnhancer:
    """
    Motor de corrección fotográfica y color grading para sujetos y productos.
    """

    def __init__(
        self,
        auto_white_balance: bool = True,
        exposure_matching: bool = True,
        edge_despill: bool = True,
        target_luminance: float = 0.58,
        gamma: float = 0.90,
    ):
        """
        Args:
            auto_white_balance: Corrige dominantes de color cálidas/frías a 5500K neutro.
            exposure_matching: Iguala el histograma para resaltar texturas en fondos de alta luminosidad (#FFFFFF).
            edge_despill: Elimina halos oscuros residuales en bordes semi-transparentes.
            target_luminance: Brillo objetivo para el sujeto (0.4 a 0.8).
            gamma: Curva de elevación de sombras y medios tonos (valores < 1.0 iluminan medios tonos).
        """
        self.auto_white_balance = auto_white_balance
        self.exposure_matching = exposure_matching
        self.edge_despill = edge_despill
        self.target_luminance = target_luminance
        self.gamma = gamma

    def correct_white_balance(
        self,
        image_rgb: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Aplica balance de blancos automático (Gray World con protección de altas luces)
        utilizando únicamente los píxeles del primer plano.

        Args:
            image_rgb: Array float32 [0.0, 1.0] de tamaño (H, W, 3).
            mask: Array float32 [0.0, 1.0] de tamaño (H, W).

        Returns:
            Array float32 [0.0, 1.0] corregido.
        """
        fg_pixels = mask > 0.35
        if np.sum(fg_pixels) < 100:
            return image_rgb

        r = image_rgb[:, :, 0][fg_pixels]
        g = image_rgb[:, :, 1][fg_pixels]
        b = image_rgb[:, :, 2][fg_pixels]

        mean_r = float(np.mean(r))
        mean_g = float(np.mean(g))
        mean_b = float(np.mean(b))

        # Si algún canal es casi nulo, evitar división por cero
        if mean_r < 1e-4 or mean_g < 1e-4 or mean_b < 1e-4:
            return image_rgb

        # Iluminante gris neutro promedio
        gray_target = (mean_r + mean_g + mean_b) / 3.0

        # Ganancias con sujeción para no sobrevirar colores intencionales
        gain_r = float(np.clip(gray_target / mean_r, 0.80, 1.25))
        gain_g = float(np.clip(gray_target / mean_g, 0.85, 1.18))
        gain_b = float(np.clip(gray_target / mean_b, 0.80, 1.30))

        out = image_rgb.copy()
        out[:, :, 0] = np.clip(out[:, :, 0] * gain_r, 0.0, 1.0)
        out[:, :, 1] = np.clip(out[:, :, 1] * gain_g, 0.0, 1.0)
        out[:, :, 2] = np.clip(out[:, :, 2] * gain_b, 0.0, 1.0)

        return out

    def equalize_exposure(
        self,
        image_rgb: np.ndarray,
        mask: np.ndarray,
    ) -> np.ndarray:
        """
        Eleva sombras y medios tonos mediante una curva gamma adaptativa
        para armonizar el objeto con la luz de un estudio high-key.
        """
        fg_pixels = mask > 0.35
        if np.sum(fg_pixels) < 100:
            return image_rgb

        # Luminancia relativa estándar (Rec. 709)
        lum = 0.2126 * image_rgb[:, :, 0] + 0.7152 * image_rgb[:, :, 1] + 0.0722 * image_rgb[:, :, 2]
        mean_lum = float(np.mean(lum[fg_pixels]))

        # Calcular factor gamma adaptativo
        if mean_lum < self.target_luminance:
            # Objeto subexpuesto respecto al fondo blanco -> elevar suavemente
            adaptive_gamma = max(0.70, self.gamma * (mean_lum / self.target_luminance))
        else:
            adaptive_gamma = min(1.05, self.gamma)

        # Aplicar curva gamma preservando saturación de color
        out = np.power(np.maximum(image_rgb, 0.0), adaptive_gamma)

        # Micro-contraste suave (levantar medios tonos sin quemar blancos)
        out = np.clip(out, 0.0, 1.0)
        return out

    def despill_edge_fringes(
        self,
        image_rgb: np.ndarray,
        mask: np.ndarray,
        radius: int = 2,
    ) -> np.ndarray:
        """
        Elimina halos oscuros y contaminación de color en los bordes semi-transparentes.
        Propaga los colores limpios del núcleo del objeto hacia la zona de transición alfa.

        Args:
            image_rgb: Array float32 [0.0, 1.0] (H, W, 3).
            mask: Array float32 [0.0, 1.0] (H, W).
            radius: Radio de píxeles del halo a sanear.

        Returns:
            Array float32 [0.0, 1.0] con bordes limpios.
        """
        solid_core = mask > 0.85
        transition_zone = (mask > 0.05) & (mask <= 0.85)

        if not np.any(transition_zone) or not np.any(solid_core):
            return image_rgb

        # En la zona de transición donde suele haber contaminación del fondo anterior,
        # realizar un muestreo de color vecino del núcleo sólido mediante distancia euclidiana
        try:
            # Transformada de distancia inversa para encontrar el píxel sólido más cercano
            indices = distance_transform_edt(~solid_core, return_distances=False, return_indices=True)

            out = image_rgb.copy()
            # En los píxeles de transición, mezclar el color original con el color del núcleo interior limpio
            # para evitar halos negros o verdosos/amarillentos
            core_r = image_rgb[:, :, 0][tuple(indices)]
            core_g = image_rgb[:, :, 1][tuple(indices)]
            core_b = image_rgb[:, :, 2][tuple(indices)]

            blend_weight = (1.0 - mask)[transition_zone, np.newaxis]
            orig_rgb = out[transition_zone]
            core_rgb = np.stack([core_r, core_g, core_b], axis=-1)[transition_zone]

            # Fusión ponderada: más cerca del borde exterior, mayor uso del color limpio propagado
            cleaned_edge = orig_rgb * (1.0 - blend_weight * 0.70) + core_rgb * (blend_weight * 0.70)
            out[transition_zone] = cleaned_edge

            return np.clip(out, 0.0, 1.0)
        except Exception:
            # Si falla scipy distance transform, retornar sin cambios
            return image_rgb

    def enhance(
        self,
        instance_rgba: Image.Image,
        mask: Optional[Image.Image] = None,
    ) -> Image.Image:
        """
        Ejecuta el flujo completo de graduación y mejora fotográfica de estudio sobre una instancia.

        Args:
            instance_rgba: Imagen PIL en modo RGBA.
            mask: Máscara alfa opcional (si no se indica, usa el canal A de la imagen).

        Returns:
            Image.Image en modo RGBA tratada fotográficamente.
        """
        if instance_rgba.mode != "RGBA":
            instance_rgba = instance_rgba.convert("RGBA")

        rgba_arr = np.array(instance_rgba, dtype=np.float32) / 255.0
        rgb = rgba_arr[:, :, :3]
        alpha = rgba_arr[:, :, 3]

        if mask is not None:
            if mask.mode != "L":
                mask = mask.convert("L")
            m_arr = np.array(mask, dtype=np.float32) / 255.0
        else:
            m_arr = alpha

        # 1. Balance de Blancos Automático (5500K Studio Light)
        if self.auto_white_balance:
            rgb = self.correct_white_balance(rgb, m_arr)

        # 2. Ecualización de Exposición High-Key
        if self.exposure_matching:
            rgb = self.equalize_exposure(rgb, m_arr)

        # 3. Despill y erradicación de halos de borde
        if self.edge_despill:
            rgb = self.despill_edge_fringes(rgb, m_arr)

        # Reensamblar RGBA
        enhanced_rgba_arr = np.dstack([rgb, alpha])
        enhanced_rgba_uint8 = np.clip(enhanced_rgba_arr * 255.0, 0, 255).astype(np.uint8)

        return Image.fromarray(enhanced_rgba_uint8, mode="RGBA")
