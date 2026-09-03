"""
Pipeline Estándar de Alto Rendimiento (Fast Path).
Ejecuta remoción de fondo monocapa ultrarrápida con BiRefNet.
"""

import logging
from pathlib import Path
from typing import Union, Tuple, Dict, Any, Optional
from PIL import Image

from core.segmenter import BiRefNetSegmenter
from core.compositor import LayeredCompositor

logger = logging.getLogger(__name__)


class StandardPipeline:
    """
    Pipeline estándar para corte rápido y composición limpia sobre fondo plano o transparente.
    """

    def __init__(
        self,
        segmenter: Optional[BiRefNetSegmenter] = None,
        compositor: Optional[LayeredCompositor] = None,
        device: str = "auto",
    ):
        self.segmenter = segmenter or BiRefNetSegmenter(model_name="birefnet-general", device=device)
        self.compositor = compositor or LayeredCompositor()

    def process(
        self,
        image_input: Union[str, Path, Image.Image],
        bg_color: str = "white",
        auto_crop: bool = False,
    ) -> Tuple[Image.Image, Dict[str, Any]]:
        """
        Procesa una imagen individual en modo monocapa de alta velocidad.

        Args:
            image_input: Ruta de archivo o imagen PIL.
            bg_color: "white", "transparent" o color Hex.
            auto_crop: Si es True, recorta márgenes vacíos alrededor del sujeto.

        Returns:
            Tuple con (Imagen final PIL, Metadatos de ejecución)
        """
        if isinstance(image_input, (str, Path)):
            img = Image.open(image_input)
        else:
            img = image_input

        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size

        # 1. Segmentación con BiRefNet
        rgba_cutout, alpha_mask = self.segmenter.segment_alpha(img)

        # 2. Auto-crop opcional
        if auto_crop:
            bbox = alpha_mask.getbbox()
            if bbox:
                # Agregar margen del 4%
                pad_x = int((bbox[2] - bbox[0]) * 0.04)
                pad_y = int((bbox[3] - bbox[1]) * 0.04)
                crop_box = (
                    max(0, bbox[0] - pad_x),
                    max(0, bbox[1] - pad_y),
                    min(w, bbox[2] + pad_x),
                    min(h, bbox[3] + pad_y),
                )
                rgba_cutout = rgba_cutout.crop(crop_box)
                alpha_mask = alpha_mask.crop(crop_box)
                w, h = rgba_cutout.size

        # 3. Composición sobre el fondo deseado (sin sombras sintéticas en modo estándar)
        layer = {
            "rgba": rgba_cutout,
            "mask": alpha_mask,
            "depth": 1.0,
            "label": "cutout",
        }

        final_img, meta = self.compositor.composite(
            layers=[layer],
            canvas_size=(w, h),
            bg_color=bg_color,
            apply_shadows=False,
        )

        metadata = {
            "mode": "standard",
            "dimensions": (w, h),
            "bg_color": bg_color,
            "auto_crop": auto_crop,
            "instances_count": 1,
        }

        return final_img, metadata
