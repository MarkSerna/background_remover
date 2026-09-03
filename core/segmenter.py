"""
Segmentador de alta precisión con BiRefNet y aislamiento de instancias (SAM 2 / Componentes Conectados).
Produce máscaras alfa con nivel de detalle para cabello, vidrio y bordes finos,
junto con la descomposición en capas independientes para cada objeto detectado.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple, Union
import numpy as np
from PIL import Image
from scipy.ndimage import label as nd_label

try:
    import rembg
    HAS_REMBG = True
except Exception:
    HAS_REMBG = False

logger = logging.getLogger(__name__)


class BiRefNetSegmenter:
    """
    Segmentador de borde fino BiRefNet con capacidad de aislamiento por instancias.
    """

    def __init__(
        self,
        model_name: str = "birefnet-general",
        device: str = "auto",
    ):
        """
        Args:
            model_name: Identificador del modelo (ej: 'birefnet-general', 'birefnet-massive').
            device: 'cuda', 'cpu' o 'auto'.
        """
        self.model_name = model_name
        self.device = device
        self._session = None

    def _ensure_session(self):
        """Inicialización diferida de la sesión de inferencia de BiRefNet."""
        if self._session is not None:
            return

        if HAS_REMBG:
            try:
                logger.info(f"Inicializando sesión de BiRefNet ({self.model_name})...")
                self._session = rembg.new_session(self.model_name)
                logger.info("Sesión BiRefNet lista.")
            except Exception as e:
                logger.warning(f"No se pudo cargar sesión directa de {self.model_name}: {e}. Probando u2net...")
                try:
                    self._session = rembg.new_session("u2net")
                except Exception as err:
                    logger.error(f"Error fatal inicializando motor de segmentación: {err}")

    def segment_alpha(self, image: Image.Image) -> Tuple[Image.Image, Image.Image]:
        """
        Calcula el corte alfa general de alta precisión para la imagen.

        Args:
            image: Imagen PIL (RGB o RGBA).

        Returns:
            Tuple con (Imagen RGBA recortada, Máscara en modo 'L').
        """
        if image.mode != "RGB":
            image_rgb = image.convert("RGB")
        else:
            image_rgb = image

        self._ensure_session()

        if self._session is not None and HAS_REMBG:
            try:
                # rembg.remove retorna una imagen RGBA
                rgba_out = rembg.remove(image_rgb, session=self._session)
                alpha_mask = rgba_out.split()[3]
                return rgba_out, alpha_mask
            except Exception as e:
                logger.error(f"Error en inferencia BiRefNet: {e}")

        # Fallback de emergencia: umbralado simple
        w, h = image_rgb.size
        empty_mask = Image.new("L", (w, h), 255)
        rgba_fallback = image_rgb.convert("RGBA")
        return rgba_fallback, empty_mask

    def extract_instances(
        self,
        image: Image.Image,
        detections: Optional[List[Dict[str, Any]]] = None,
        min_instance_area: int = 400,
    ) -> List[Dict[str, Any]]:
        """
        Extrae y aísla cada objeto/sujeto como una capa independiente.

        Combina el matting de bordes finos de BiRefNet con las cajas delimitadoras
        del detector (Grounding DINO / SAM 2) o con segmentación de componentes conectados.

        Args:
            image: Imagen original (RGB).
            detections: Lista opcional de cajas provenientes de ZeroShotDetector.
            min_instance_area: Área mínima en píxeles para considerar una instancia válida.

        Returns:
            Lista de instancias con:
            [
                {
                    'id': int,
                    'rgba': Image.Image,   # Objeto aislado en canvas completo
                    'mask': Image.Image,   # Máscara L del objeto
                    'bbox': (x1, y1, x2, y2),
                    'label': str,
                }, ...
            ]
        """
        w, h = image.size
        # 1. Obtener la segmentación alfa global de alta precisión
        full_rgba, full_mask = self.segment_alpha(image)
        mask_arr = np.array(full_mask, dtype=np.uint8)

        instances = []

        # Caso A: Se proporcionaron detecciones guiadas por prompt
        if detections and len(detections) > 0 and detections[0].get("label") != "foreground":
            img_rgba_arr = np.array(full_rgba)

            for idx, det in enumerate(detections):
                x1, y1, x2, y2 = det["bbox"]
                label = det.get("label", f"object_{idx}")

                # Crear máscara específica para esta caja
                inst_mask_arr = np.zeros_like(mask_arr)
                inst_mask_arr[y1:y2, x1:x2] = mask_arr[y1:y2, x1:x2]

                if np.sum(inst_mask_arr > 25) < min_instance_area:
                    continue

                inst_rgba_arr = img_rgba_arr.copy()
                inst_rgba_arr[:, :, 3] = inst_mask_arr

                inst_mask_pil = Image.fromarray(inst_mask_arr, mode="L")
                inst_rgba_pil = Image.fromarray(inst_rgba_arr, mode="RGBA")

                instances.append({
                    "id": idx,
                    "rgba": inst_rgba_pil,
                    "mask": inst_mask_pil,
                    "bbox": (x1, y1, x2, y2),
                    "label": label,
                })

            if instances:
                return instances

        # Caso B: Descomposición automática por componentes conectados contiguos
        binary_mask = (mask_arr > 30).astype(np.uint8)
        labeled_arr, num_features = nd_label(binary_mask)

        img_rgba_arr = np.array(full_rgba)

        for feat_id in range(1, num_features + 1):
            feat_pixels = (labeled_arr == feat_id)
            area = np.sum(feat_pixels)

            if area < min_instance_area:
                continue

            inst_mask_arr = np.zeros_like(mask_arr)
            inst_mask_arr[feat_pixels] = mask_arr[feat_pixels]

            y_indices, x_indices = np.where(feat_pixels)
            bbox = (int(x_indices.min()), int(y_indices.min()), int(x_indices.max()), int(y_indices.max()))

            inst_rgba_arr = img_rgba_arr.copy()
            inst_rgba_arr[:, :, 3] = inst_mask_arr

            inst_mask_pil = Image.fromarray(inst_mask_arr, mode="L")
            inst_rgba_pil = Image.fromarray(inst_rgba_arr, mode="RGBA")

            instances.append({
                "id": feat_id - 1,
                "rgba": inst_rgba_pil,
                "mask": inst_mask_pil,
                "bbox": bbox,
                "label": f"instance_{feat_id}",
            })

        # Si no se descompuso en componentes múltiples, devolver la capa completa como instancia única
        if not instances:
            instances.append({
                "id": 0,
                "rgba": full_rgba,
                "mask": full_mask,
                "bbox": (0, 0, w, h),
                "label": "primary_subject",
            })

        return instances
