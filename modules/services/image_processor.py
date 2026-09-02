"""Servicio de procesamiento y composición de imágenes con Pillow."""

import logging
from pathlib import Path
from typing import Tuple, Optional
from PIL import Image, ImageOps, ImageDraw
import numpy as np

from modules.models.config import ProcessingConfig
from modules.utils.helpers import parse_color_string

logger = logging.getLogger(__name__)


class ImageProcessor:
    """Maneja la composición de fondos, recorte (crop), padding y guardado de imágenes."""

    def __init__(self, config: Optional[ProcessingConfig] = None):
        self.config = config or ProcessingConfig()

    def apply_solid_background(
        self,
        rgba_image: Image.Image,
        bg_color: Optional[Tuple[int, int, int, int]] = None,
        original_image: Optional[Image.Image] = None,
        cleanup_residual: bool = True
    ) -> Image.Image:
        """
        Compone la imagen con fondo transparente sobre un fondo solido (blanco por defecto).
        Si cleanup_residual=True, elimina islas de fondo residual que rembg no capturo.
        """
        target_color = bg_color or parse_color_string(self.config.bg_color_raw)

        # Limpiar residuos del fondo antes de compositar
        if cleanup_residual and original_image is not None:
            rgba_image = self._cleanup_residual_background(rgba_image, original_image)

        # Si el color de destino es transparente
        if target_color[3] == 0:
            return rgba_image

        # Crear capa de fondo solido con las mismas dimensiones
        background = Image.new("RGBA", rgba_image.size, target_color)

        # Superponer el sujeto usando su propio canal alfa como mascara de recorte
        background.paste(rgba_image, (0, 0), rgba_image)

        # Convertir a RGB para eliminar el canal alfa (ideal para JPEG / fondos blancos limpios)
        if self.config.output_format == "JPEG" or target_color[3] == 255:
            return background.convert("RGB")

        return background

    def _cleanup_residual_background(
        self,
        rgba_image: Image.Image,
        original_image: Image.Image,
        tolerance: int = 30
    ) -> Image.Image:
        """
        Elimina islas de fondo residual que rembg no capturo completamente.

        Estrategia:
          1. Muestrea el color de fondo desde las 4 esquinas de la imagen original.
          2. Crea una mascara binaria de pixeles que coinciden con ese color (con tolerancia).
          3. Expande la mascara desde los bordes (flood-fill) para capturar solo el exterior.
          4. Pone alfa=0 en esos pixeles residuales del RGBA resultante.
        """
        try:
            orig = original_image.convert("RGB").resize(rgba_image.size, Image.BILINEAR)
            w, h = orig.size

            # Muestrear color de fondo desde las esquinas (promedio de 5x5 px de cada esquina)
            def corner_avg(cx, cy):
                region = orig.crop((cx, cy, cx + 5, cy + 5))
                pixels = list(region.getdata())
                r = sum(p[0] for p in pixels) // len(pixels)
                g = sum(p[1] for p in pixels) // len(pixels)
                b = sum(p[2] for p in pixels) // len(pixels)
                return (r, g, b)

            corners = [
                corner_avg(0, 0),
                corner_avg(w - 6, 0),
                corner_avg(0, h - 6),
                corner_avg(w - 6, h - 6),
            ]
            # Color de fondo representativo: mediana de las esquinas
            bg_r = sorted(c[0] for c in corners)[1]
            bg_g = sorted(c[1] for c in corners)[1]
            bg_b = sorted(c[2] for c in corners)[1]
            bg_ref = (bg_r, bg_g, bg_b)

            # Crear mascara de similitud con el color de fondo
            orig_arr = np.array(orig, dtype=np.int32)
            diff = np.abs(orig_arr[:, :, 0] - bg_r) + \
                   np.abs(orig_arr[:, :, 1] - bg_g) + \
                   np.abs(orig_arr[:, :, 2] - bg_b)
            similar_mask = (diff <= tolerance * 3).astype(np.uint8) * 255

            # Flood-fill desde cada esquina para capturar solo fondo conectado al exterior
            mask_img = Image.fromarray(similar_mask, mode="L")
            flood_mask = Image.new("L", (w, h), 0)
            draw = ImageDraw.Draw(flood_mask)

            seed_points = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]
            for seed in seed_points:
                if similar_mask[seed[1], seed[0]] == 255:
                    ImageDraw.floodfill(mask_img, seed, 128, thresh=10)

            # Los pixeles marcados con 128 son fondo conectado al borde
            mask_arr = np.array(mask_img)
            exterior_bg = (mask_arr == 128)

            # Aplicar: poner alfa=0 donde hay fondo residual exterior
            rgba_arr = np.array(rgba_image)
            rgba_arr[exterior_bg, 3] = 0
            result = Image.fromarray(rgba_arr, mode="RGBA")
            logger.debug(f"[Cleanup] Eliminados {exterior_bg.sum()} pixeles de fondo residual")
            return result

        except Exception as e:
            logger.warning(f"[Cleanup] No se pudo limpiar fondo residual: {e}. Continuando sin limpieza.")
            return rgba_image

    def auto_crop_and_pad(
        self,
        image: Image.Image,
        padding_percent: Optional[int] = None
    ) -> Image.Image:
        """
        Recorta el espacio sobrante alrededor del sujeto y agrega un margen uniforme.
        """
        pad_pct = self.config.padding_percent if padding_percent is None else padding_percent
        
        # Obtener bounding box del contenido (si tiene canal alfa)
        if image.mode in ("RGBA", "LA"):
            bbox = image.getbbox()
        else:
            # Para imágenes RGB, calcular contra blanco o fondo
            inverted = ImageOps.invert(image.convert("RGB"))
            bbox = inverted.getbbox()

        if not bbox:
            return image

        cropped = image.crop(bbox)
        
        if pad_pct <= 0:
            return cropped

        # Calcular tamaño del lienzo con padding
        w, h = cropped.size
        pad_w = int(w * (pad_pct / 100.0))
        pad_h = int(h * (pad_pct / 100.0))
        new_w = w + 2 * pad_w
        new_h = h + 2 * pad_h

        # Color base para padding
        bg_color = parse_color_string(self.config.bg_color_raw)
        mode = "RGBA" if image.mode == "RGBA" else "RGB"
        base_color = bg_color if mode == "RGBA" else bg_color[:3]

        padded = Image.new(mode, (new_w, new_h), base_color)
        padded.paste(cropped, (pad_w, pad_h), cropped if mode == "RGBA" else None)
        return padded

    def save_image(
        self,
        image: Image.Image,
        output_path: Path,
        dpi: Optional[Tuple[int, int]] = None
    ) -> Path:
        """
        Guarda la imagen en disco asegurando directorios y aplicando compresión y formato.
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        fmt = self.config.output_format.upper()
        save_kwargs = {}
        
        if fmt == "JPEG" or output_path.suffix.lower() in [".jpg", ".jpeg"]:
            fmt = "JPEG"
            if image.mode != "RGB":
                image = image.convert("RGB")
            save_kwargs = {
                "quality": self.config.output_quality,
                "optimize": True,
                "progressive": True
            }
        elif fmt == "PNG" or output_path.suffix.lower() == ".png":
            fmt = "PNG"
            save_kwargs = {
                "optimize": True
            }
        elif fmt == "WEBP" or output_path.suffix.lower() == ".webp":
            fmt = "WEBP"
            save_kwargs = {
                "quality": self.config.output_quality,
                "method": 6
            }

        if dpi:
            save_kwargs["dpi"] = dpi

        image.save(output_path, format=fmt, **save_kwargs)
        logger.debug(f"Imagen guardada exitosamente en {output_path} [{fmt}]")
        return output_path
