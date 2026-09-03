"""
Estimador de profundidad monocular basado en Depth Anything V2.
Extrae mapas de profundidad métricos/relativos y calcula el valor medio Z
para ordenar capas de objetos en el espacio 3D de la escena.
"""

import logging
from typing import Optional, Union, Tuple
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class DepthEstimator:
    """
    Estimador de profundidad monocular para asignación de Z-index
    utilizando Depth Anything V2.
    """

    def __init__(
        self,
        model_name: str = "depth-anything/Depth-Anything-V2-Small-hf",
        device: str = "auto",
    ):
        """
        Args:
            model_name: Identificador del modelo en Hugging Face Hub.
            device: 'cuda', 'cpu' o 'auto' para selección automática.
        """
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self._pipe = None
        self._load_failed = False

    def _resolve_device(self, device: str) -> str:
        if device == "auto":
            try:
                import torch
                return "cuda" if torch.cuda.is_available() else "cpu"
            except Exception:
                return "cpu"
        return device

    def _ensure_model(self):
        """Inicialización perezosa (lazy loading) del pipeline de transformers."""
        if self._pipe is not None or self._load_failed:
            return

        try:
            import torch
            from transformers import pipeline

            device_idx = 0 if self.device == "cuda" else -1
            logger.info(f"Cargando modelo de profundidad '{self.model_name}' en {self.device}...")
            self._pipe = pipeline(
                task="depth-estimation",
                model=self.model_name,
                device=device_idx,
            )
            logger.info("Modelo Depth Anything V2 cargado exitosamente.")
        except Exception as e:
            logger.warning(
                f"No se pudo cargar {self.model_name} ({e}). "
                "Se empleará estimación geométrica basada en perspectiva de plano de suelo."
            )
            self._load_failed = True

    def estimate_depth(self, image: Image.Image) -> np.ndarray:
        """
        Infiere el mapa de profundidad para la imagen dada.

        Args:
            image: Imagen PIL (RGB).

        Returns:
            np.ndarray 2D float32 con valores normalizados [0.0, 1.0],
            donde 1.0 es el punto más cercano a la cámara y 0.0 el más lejano.
        """
        if image.mode != "RGB":
            image = image.convert("RGB")

        w, h = image.size
        self._ensure_model()

        if self._pipe is not None:
            try:
                output = self._pipe(image)
                # El output es un diccionario con 'depth' como PIL Image
                depth_img = output.get("depth")
                if depth_img is not None:
                    depth_arr = np.array(depth_img, dtype=np.float32)
                    d_min, d_max = depth_arr.min(), depth_arr.max()
                    if d_max > d_min:
                        depth_norm = (depth_arr - d_min) / (d_max - d_min)
                    else:
                        depth_norm = np.ones_like(depth_arr) * 0.5
                    return depth_norm
            except Exception as e:
                logger.debug(f"Error durante inferencia de profundidad: {e}")

        # Fallback geométrico inteligente:
        # En fotografía de producto y retratos, los objetos situados más abajo en el encuadre
        # descansan sobre el plano de suelo y están más próximos al observador.
        y_coords = np.linspace(0.1, 1.0, h, dtype=np.float32)[:, np.newaxis]
        return np.repeat(y_coords, w, axis=1)

    def calculate_instance_depth(
        self,
        depth_map: np.ndarray,
        mask: Union[Image.Image, np.ndarray],
    ) -> float:
        """
        Calcula el valor Z representativo (mediana ponderada) para una máscara de instancia.

        Args:
            depth_map: Mapa 2D de profundidad [0.0, 1.0].
            mask: Máscara binaria o alfa de la instancia (PIL 'L' o numpy 2D).

        Returns:
            float con el valor Z (mayor = más cerca de la cámara / primer plano).
        """
        if isinstance(mask, Image.Image):
            if mask.mode != "L":
                mask = mask.convert("L")
            mask_arr = np.array(mask, dtype=np.float32) / 255.0
        else:
            mask_arr = np.array(mask, dtype=np.float32)
            if mask_arr.max() > 1.0:
                mask_arr /= 255.0

        # Redimensionar el mapa si las dimensiones no coinciden exactamente
        if depth_map.shape != mask_arr.shape:
            d_img = Image.fromarray((depth_map * 255).astype(np.uint8), mode="L")
            d_img = d_img.resize((mask_arr.shape[1], mask_arr.shape[0]), Image.Resampling.BILINEAR)
            depth_map = np.array(d_img, dtype=np.float32) / 255.0

        foreground_pixels = depth_map[mask_arr > 0.2]
        if len(foreground_pixels) == 0:
            return 0.5

        # Usar percentil 65 para representar mejor la superficie frontal del objeto
        return float(np.percentile(foreground_pixels, 65))
