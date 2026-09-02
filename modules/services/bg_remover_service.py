"""Servicio de eliminación de fondo con IA mediante rembg y sesiones ONNX optimizadas."""

import logging
import io
from typing import Optional, Dict, Any
from PIL import Image
import rembg

from modules.models.config import ProcessingConfig
from modules.models.error_codes import ErrorCode
from modules.utils.helpers import CircuitBreaker, CircuitBreakerOpenException
from modules.services.model_selector import ModelSelector, ModelSelectionResult

logger = logging.getLogger(__name__)


class BackgroundRemoverService:
    """Maneja las sesiones de remoción de fondo y la inferencia de modelos ONNX."""

    def __init__(self, processing_config: Optional[ProcessingConfig] = None):
        self.config = processing_config or ProcessingConfig()
        self.sessions: Dict[str, Any] = {}
        self.circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=45.0)
        self.model_selector = ModelSelector()
        self.last_selection: Optional[ModelSelectionResult] = None
        # 'auto' no es un modelo real de rembg; se resuelve por imagen en tiempo de inferencia
        if self.config.model_name not in (None, "auto"):
            self._preload_session(self.config.model_name)

    def _preload_session(self, model_name: str) -> None:
        """Inicializa y almacena en caché la sesión de rembg para el modelo especificado."""
        try:
            logger.info(f"Cargando sesión de rembg con modelo: '{model_name}'...")
            self.sessions[model_name] = rembg.new_session(model_name)
            logger.info(f"Modelo '{model_name}' listo y cargado en memoria.")
        except Exception as e:
            logger.error(f"Error al cargar sesión de modelo '{model_name}': {e}")
            # Se intentará cargar de nuevo bajo demanda

    def get_session(self, model_name: str):
        """Obtiene una sesión existente o crea una nueva si no existe."""
        if model_name not in self.sessions:
            try:
                self.sessions[model_name] = rembg.new_session(model_name)
            except Exception as e:
                logger.error(f"Fallo al inicializar sesión para '{model_name}': {e}")
                raise
        return self.sessions[model_name]

    def remove_background(
        self,
        image: Image.Image,
        model_name: Optional[str] = None,
        alpha_matting: Optional[bool] = None
    ) -> Image.Image:
        """
        Ejecuta la remoción de fondo sobre una imagen PIL y retorna la imagen con canal alfa (RGBA).
        Si model_name es None o 'auto', el selector automático elige el modelo óptimo para la imagen.
        """
        if not self.circuit_breaker.can_execute():
            raise CircuitBreakerOpenException("CircuitBreaker abierto: Demasiados fallos recientes de inferencia.")

        # --- Selección automática de modelo ---
        configured_model = model_name or self.config.model_name
        if configured_model in (None, "auto"):
            self.last_selection = self.model_selector.select(image)
            model = self.last_selection.model_name
            logger.info(
                f"[Auto-Select] '{model}' elegido con {self.last_selection.confidence:.0%} confianza. "
                f"Razon: {self.last_selection.reason}"
            )
        else:
            model = configured_model
            self.last_selection = None

        use_alpha_matting = self.config.alpha_matting if alpha_matting is None else alpha_matting

        try:
            session = self.get_session(model)

            # Convertir imagen PIL a bytes para rembg
            buffered = io.BytesIO()
            # Asegurar formato compatible
            image.save(buffered, format="PNG")
            img_bytes = buffered.getvalue()

            # Ejecutar inferencia rembg
            output_bytes = rembg.remove(
                img_bytes,
                session=session,
                alpha_matting=use_alpha_matting,
                alpha_matting_foreground_threshold=self.config.alpha_matting_fg_threshold,
                alpha_matting_background_threshold=self.config.alpha_matting_bg_threshold,
                alpha_matting_erode_size=self.config.alpha_matting_erode_size
            )

            # Cargar imagen procesada en PIL como RGBA
            output_image = Image.open(io.BytesIO(output_bytes)).convert("RGBA")
            
            # Post-procesamiento: Eliminar ruido y neblina de fondo con alfa muy bajo (< 50)
            import numpy as np
            arr = np.array(output_image)
            alpha = arr[:, :, 3]
            # Todo pixel semi-transparente residual en áreas de fondo (< 60) se anula a 0
            arr[alpha < 60, 3] = 0
            output_image = Image.fromarray(arr, mode="RGBA")
            
            self.circuit_breaker.record_success()
            return output_image

        except Exception as e:
            self.circuit_breaker.record_failure()
            logger.error(f"Error durante remoción de fondo: {e}")
            raise
