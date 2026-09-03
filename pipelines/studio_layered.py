"""
Pipeline de Estudio Estratificado Multicapa (Studio Layered Pipeline).
Flujo avanzado en 5 etapas:
  1. Detección Zero-Shot guiada por texto libre (Grounding DINO / OWL-ViT)
  2. Segmentación de bordes finos y aislamiento de instancias (BiRefNet + SAM 2)
  3. Estimación de profundidad monocular y ordenamiento Z-index (Depth Anything V2)
  4. Síntesis de sombras de contacto realistas (Ambient Occlusion en base de contacto)
  5. Composición estratificada Back-to-Front sobre lienzo fotográfico de estudio
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

logger = logging.getLogger(__name__)


class StudioLayeredPipeline:
    """
    Pipeline avanzado de estudio fotográfico con aislamiento de instancias,
    inferencia de profundidad y sombras de contacto volumétricas.
    """

    def __init__(
        self,
        segmenter: Optional[BiRefNetSegmenter] = None,
        detector: Optional[ZeroShotDetector] = None,
        depth_estimator: Optional[DepthEstimator] = None,
        shadow_generator: Optional[ContactShadowGenerator] = None,
        compositor: Optional[LayeredCompositor] = None,
        device: str = "auto",
    ):
        self.device = device
        self.segmenter = segmenter or BiRefNetSegmenter(device=device)
        self.detector = detector or ZeroShotDetector(device=device)
        self.depth_estimator = depth_estimator or DepthEstimator(device=device)
        self.shadow_generator = shadow_generator or ContactShadowGenerator()
        self.compositor = compositor or LayeredCompositor(shadow_generator=self.shadow_generator)

    def process(
        self,
        image_input: Union[str, Path, Image.Image],
        text_prompt: Optional[str] = None,
        bg_color: str = "white",
        apply_shadows: bool = True,
        shadow_intensity: float = 0.65,
        shadow_blur: float = 12.0,
        auto_crop: bool = False,
    ) -> Tuple[Image.Image, Dict[str, Any]]:
        """
        Ejecuta el pipeline multicapa de estudio completo.

        Args:
            image_input: Ruta o imagen PIL de entrada.
            text_prompt: Prompt de texto opcional para guiar la detección de instancias (ej: 'product, shoes').
            bg_color: Fondo ('white', 'transparent', o código Hex '#FFFFFF').
            apply_shadows: Si se deben proyectar sombras de contacto.
            shadow_intensity: Intensidad de la sombra (0.0 a 1.0).
            shadow_blur: Radio de desenfoque de la sombra.
            auto_crop: Si es True, recorta el encuadre final al contenido útil.

        Returns:
            Tuple con (Imagen final PIL compuesta, Diccionario con metadatos de las capas e inferencia)
        """
        if isinstance(image_input, (str, Path)):
            img = Image.open(image_input)
        else:
            img = image_input

        if img.mode != "RGB":
            img = img.convert("RGB")

        w, h = img.size
        logger.info(f"Iniciando Studio Pipeline para imagen de {w}x{h}...")

        # -------------------------------------------------------------
        # Etapa 1: Detección Zero-Shot guiada por texto
        # -------------------------------------------------------------
        detections = []
        if text_prompt and text_prompt.strip():
            logger.info(f"Etapa 1: Detectando instancias con prompt '{text_prompt}'...")
            detections = self.detector.detect(img, text_prompt=text_prompt)

        # -------------------------------------------------------------
        # Etapa 2: Segmentación y Aislamiento de Instancias (BiRefNet + SAM 2)
        # -------------------------------------------------------------
        logger.info("Etapa 2: Aislamiento de instancias con BiRefNet...")
        instances = self.segmenter.extract_instances(img, detections=detections)
        logger.info(f"Se aislaron {len(instances)} capa(s) de instancias.")

        # -------------------------------------------------------------
        # Etapa 3: Estimación de Profundidad Monocular (Depth Anything V2)
        # -------------------------------------------------------------
        logger.info("Etapa 3: Estimando mapa de profundidad 3D...")
        depth_map = self.depth_estimator.estimate_depth(img)

        # Asignar Z-depth a cada instancia
        for inst in instances:
            z_val = self.depth_estimator.calculate_instance_depth(depth_map, inst["mask"])
            inst["depth"] = z_val

        # -------------------------------------------------------------
        # Etapa 4 y 5: Sombras de Contacto y Composición Estratificada
        # -------------------------------------------------------------
        logger.info("Etapas 4 y 5: Generando sombras y componiendo en orden Z...")
        final_img, layer_metadata = self.compositor.composite(
            layers=instances,
            canvas_size=(w, h),
            bg_color=bg_color,
            apply_shadows=apply_shadows,
            shadow_intensity=shadow_intensity,
            shadow_blur=shadow_blur,
        )

        # Auto-crop opcional
        if auto_crop:
            # Combinar todas las máscaras para calcular el bounding box global
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
            "shadow_intensity": shadow_intensity,
            "shadow_blur": shadow_blur,
            "prompt": text_prompt,
            "layers_count": len(instances),
            "layers": layer_metadata,
        }

        logger.info("Studio Layered Pipeline completado exitosamente.")
        return final_img, metadata
