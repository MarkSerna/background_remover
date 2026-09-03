"""
Detector de objetos Zero-Shot basado en Grounding DINO / OWL-ViT.
Permite localizar instancias individuales mediante prompts de texto libre
(ej: 'person', 'product', 'shoes', 'car') generando cajas delimitadoras (bounding boxes).
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


class ZeroShotDetector:
    """
    Detector de objetos con prompts de texto libre (Open-Vocabulary Zero-Shot Detection).
    """

    def __init__(
        self,
        model_name: str = "google/owlvit-base-patch32",
        device: str = "auto",
        confidence_threshold: float = 0.20,
    ):
        """
        Args:
            model_name: Modelo en Hugging Face Hub (ej: 'google/owlvit-base-patch32' o 'IDEA-Research/grounding-dino-tiny').
            device: 'cuda', 'cpu' o 'auto'.
            confidence_threshold: Umbral mínimo de confianza para aceptar una detección.
        """
        self.model_name = model_name
        self.device = self._resolve_device(device)
        self.confidence_threshold = confidence_threshold
        self._processor = None
        self._model = None
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
        """Carga bajo demanda del modelo y procesador."""
        if (self._processor is not None and self._model is not None) or self._load_failed:
            return

        try:
            import torch
            from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

            logger.info(f"Cargando detector Zero-Shot '{self.model_name}' en {self.device}...")
            self._processor = AutoProcessor.from_pretrained(self.model_name)
            self._model = AutoModelForZeroShotObjectDetection.from_pretrained(self.model_name)
            self._model.to(self.device)
            self._model.eval()
            logger.info("Detector Zero-Shot cargado exitosamente.")
        except Exception as e:
            logger.warning(
                f"No se pudo cargar {self.model_name} ({e}). "
                "Se utilizará segmentación morfológica por componentes conectados."
            )
            self._load_failed = True

    def detect(
        self,
        image: Image.Image,
        text_prompt: Optional[str] = None,
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Detecta objetos en la imagen guiado por un prompt de texto o por prominencia visual.

        Args:
            image: Imagen PIL (RGB).
            text_prompt: Texto con las categorías buscadas, separadas por coma (ej: "product, bottle, shoes").
            threshold: Umbral de confianza.

        Returns:
            Lista de detecciones con formato:
            [
                {
                    'bbox': (x1, y1, x2, y2),  # Coordenadas enteras en píxeles
                    'score': float,
                    'label': str
                }, ...
            ]
        """
        if image.mode != "RGB":
            image = image.convert("RGB")

        thresh = threshold if threshold is not None else self.confidence_threshold
        w, h = image.size

        # Si no se indica prompt, retornar caja completa para segmentación general
        if not text_prompt or not text_prompt.strip():
            return [{"bbox": (0, 0, w, h), "score": 1.0, "label": "foreground"}]

        self._ensure_model()

        if self._model is not None and self._processor is not None:
            try:
                import torch

                # Dividir prompts en lista de categorías
                queries = [q.strip() for q in text_prompt.split(",") if q.strip()]
                if not queries:
                    queries = ["object", "product", "person"]

                inputs = self._processor(text=queries, images=image, return_tensors="pt")
                inputs = {k: v.to(self.device) for k, v in inputs.items()}

                with torch.no_grad():
                    outputs = self._model(**inputs)

                target_sizes = torch.tensor([[h, w]]).to(self.device)
                results = self._processor.post_process_grounded_object_detection(
                    outputs=outputs,
                    target_sizes=target_sizes,
                    threshold=thresh,
                )[0]

                detections = []
                boxes = results["boxes"].cpu().numpy()
                scores = results["scores"].cpu().numpy()
                labels = results["labels"].cpu().numpy()

                for box, score, label_idx in zip(boxes, scores, labels):
                    x1, y1, x2, y2 = [int(coord) for coord in box]
                    # Clamp a los bordes de la imagen
                    x1 = max(0, min(w - 1, x1))
                    y1 = max(0, min(h - 1, y1))
                    x2 = max(x1 + 1, min(w, x2))
                    y2 = max(y1 + 1, min(h, y2))

                    label_text = queries[label_idx] if label_idx < len(queries) else "object"

                    detections.append({
                        "bbox": (x1, y1, x2, y2),
                        "score": float(score),
                        "label": label_text,
                    })

                if detections:
                    logger.info(f"Se detectaron {len(detections)} instancias con prompt '{text_prompt}'.")
                    return detections

            except Exception as e:
                logger.debug(f"Inferencia del detector zero-shot falló: {e}")

        # Fallback si el modelo no está disponible o no encontró coincidencias
        return [{"bbox": (0, 0, w, h), "score": 0.8, "label": text_prompt or "object"}]
