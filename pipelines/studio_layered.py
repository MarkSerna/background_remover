"""
Pipeline de Estudio Estratificado Multicapa (Studio Layered Pipeline).
Cadena de procesamiento fotográfico profesional en 5 fases:
  1. Detección Zero-Shot guiada por texto libre (Grounding DINO / OWL-ViT)
  2. Segmentación de bordes finos y aislamiento de instancias (BiRefNet + SAM 2)
  3. Estimación de profundidad monocular y ordenamiento Z-index (Depth Anything V2)
  4. Mejora fotográfica y graduación de estudio (Balance de Blancos 5500K + Exposición High-Key + Despill)
  5. Síntesis de sombras de contacto (Footprint AO) y composición estratificada sobre degradado de horizonte
"""

import logging
from pathlib import Path
from typing import Union, Tuple, Dict, Any, Optional, List
from PIL import Image

from core.segmenter import BiRefNetSegmenter
from core.detector import ZeroShotDetector
from core.depth import DepthEstimator
from core.shadow import ContactShadowGenerator
from core.compositor import LayeredCompositor
from core.enhancer import StudioEnhancer

logger = logging.getLogger(__name__)


class StudioLayeredPipeline:
    """
    Pipeline fotográfico de estudio profesional con corrección de iluminación,
    despill de bordes, sombras de oclusión ambiental y fondo con perspectiva 3D.
    """

    def __init__(
        self,
        segmenter: Optional[BiRefNetSegmenter] = None,
        detector: Optional[ZeroShotDetector] = None,
        depth_estimator: Optional[DepthEstimator] = None,
        shadow_generator: Optional[ContactShadowGenerator] = None,
        compositor: Optional[LayeredCompositor] = None,
        enhancer: Optional[StudioEnhancer] = None,
        device: str = "auto",
    ):
        self.device = device
        self.segmenter = segmenter or BiRefNetSegmenter(device=device)
        self.detector = detector or ZeroShotDetector(device=device)
        self.depth_estimator = depth_estimator or DepthEstimator(device=device)
        self.shadow_generator = shadow_generator or ContactShadowGenerator()
        self.compositor = compositor or LayeredCompositor(shadow_generator=self.shadow_generator)
        self.enhancer = enhancer or StudioEnhancer()

    def process(
        self,
        image_input: Union[str, Path, Image.Image],
        text_prompt: Optional[str] = None,
        bg_color: str = "white",
        apply_shadows: bool = True,
        enhance_colors: bool = True,
        use_ground_gradient: bool = True,
        shadow_intensity: float = 0.65,
        shadow_blur: float = 12.0,
        auto_crop: bool = False,
    ) -> Tuple[Image.Image, Dict[str, Any]]:
        """
        Ejecuta la cadena completa de producción de estudio fotográfico.

        Cadena de ejecución:
          Segment -> Depth Sort -> Enhance/Color Balance -> Generate Footprint Shadows -> Final Composite

        Args:
            image_input: Ruta o imagen PIL de entrada.
            text_prompt: Prompt de texto para filtrar/detectar instancias específicas.
            bg_color: Fondo ('white', 'transparent', o código Hex).
            apply_shadows: Si se deben generar sombras de contacto de oclusión ambiental.
            enhance_colors: Si se debe aplicar corrección de balance de blancos 5500K y despill de bordes.
            use_ground_gradient: Si se debe aplicar el suave degradado de horizonte de ciclorama (#FFFFFF -> #F4F4F4).
            shadow_intensity: Factor de opacidad de la sombra (0.0 a 1.0).
            shadow_blur: Radio de difusión de la sombra.
            auto_crop: Si es True, recorta márgenes vacíos.

        Returns:
            Tuple con (Imagen final PIL tratada, Diccionario de metadatos de producción)
        """
        if isinstance(image_input, (str, Path)):
            img = Image.open(image_input)
        else:
            img = image_input

        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        logger.info(f"Iniciando Studio Pipeline fotográfico ({w}x{h})...")

        # -------------------------------------------------------------
        # 1. Detección Zero-Shot opcional por texto
        # -------------------------------------------------------------
        detections = []
        if text_prompt and text_prompt.strip():
            logger.info(f"1/5: Localizando instancias con prompt: '{text_prompt}'...")
            detections = self.detector.detect(img, text_prompt=text_prompt)

        # -------------------------------------------------------------
        # 2. Segmentación de bordes finos e instancias (BiRefNet)
        # -------------------------------------------------------------
        logger.info("2/5: Segmentación y aislamiento de instancias con BiRefNet...")
        instances = self.segmenter.extract_instances(img, detections=detections)
        logger.info(f"     Se extrajeron {len(instances)} capa(s).")

        # -------------------------------------------------------------
        # 3. Estimación de profundidad monocular y ordenamiento Z (Depth Anything V2)
        # -------------------------------------------------------------
        logger.info("3/5: Estimando mapa 3D y ordenando capas por profundidad Z...")
        depth_map = self.depth_estimator.estimate_depth(img)

        for inst in instances:
            z_val = self.depth_estimator.calculate_instance_depth(depth_map, inst["mask"])
            inst["depth"] = z_val

        # Ordenar de menor a mayor profundidad (del fondo hacia el frente)
        instances.sort(key=lambda x: x["depth"])

        # -------------------------------------------------------------
        # 4. Mejora fotográfica, Balance de Blancos y Despill de bordes
        # -------------------------------------------------------------
        if enhance_colors:
            logger.info("4/5: Aplicando graduación de estudio (White Balance 5500K + Exposición + Despill)...")
            for inst in instances:
                inst["rgba"] = self.enhancer.enhance(inst["rgba"], inst["mask"])
        else:
            logger.info("4/5: Graduación fotográfica omitida por configuración.")

        # -------------------------------------------------------------
        # 5. Huellas de sombra (Footprint AO) y Composición de Estudio
        # -------------------------------------------------------------
        logger.info("5/5: Mapeando sombras de contacto en suelo y componiendo sobre ciclorama...")
        final_img, layer_metadata = self.compositor.composite(
            layers=instances,
            canvas_size=(w, h),
            bg_color=bg_color,
            apply_shadows=apply_shadows,
            use_ground_gradient=use_ground_gradient,
            shadow_intensity=shadow_intensity,
            shadow_blur=shadow_blur,
        )

        # Auto-crop opcional
        if auto_crop:
            combined_mask = Image.new("L", (w, h), 0)
            for inst in instances:
                combined_mask.paste(inst["mask"], (0, 0), inst["mask"])
            bbox = combined_mask.getbbox()
            if bbox:
                pad_x = int((bbox[2] - bbox[0]) * 0.05)
                pad_y = int((bbox[3] - bbox[1]) * 0.05)
                crop_box = (
                    max(0, bbox[0] - pad_x),
                    max(0, bbox[1] - pad_y),
                    min(w, bbox[2] + pad_x),
                    min(h, bbox[3] + pad_y),
                )
                final_img = final_img.crop(crop_box)

        metadata = {
            "mode": "studio_layered",
            "dimensions": final_img.size,
            "bg_color": bg_color,
            "apply_shadows": apply_shadows,
            "enhance_colors": enhance_colors,
            "use_ground_gradient": use_ground_gradient,
            "shadow_intensity": shadow_intensity,
            "shadow_blur": shadow_blur,
            "prompt": text_prompt,
            "layers_count": len(instances),
            "layers": layer_metadata,
        }

        logger.info("Studio Layered Pipeline completado con éxito.")
        return final_img, metadata
