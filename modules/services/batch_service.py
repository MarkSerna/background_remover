"""Servicio de orquestación y procesamiento por lotes concurrente."""

import sys
import time
import logging
from pathlib import Path
from typing import List, Optional, Tuple, Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageOps
from tqdm import tqdm


from modules.models.config import AppConfig, ProcessingConfig
from modules.models.error_codes import ErrorCode
from modules.services.bg_remover_service import BackgroundRemoverService
from modules.services.image_processor import ImageProcessor
from modules.services.file_manager import FileManager
from modules.services.tracker_service import ProcessingTracker
from modules.utils.helpers import parse_color_string, format_bytes

logger = logging.getLogger(__name__)


class BatchProcessingService:
    """Orquesta el flujo completo de remoción, composición y guardado para una o múltiples imágenes."""

    def __init__(
        self,
        app_config: Optional[AppConfig] = None,
        remover_service: Optional[BackgroundRemoverService] = None,
        image_processor: Optional[ImageProcessor] = None,
        file_manager: Optional[FileManager] = None,
        tracker: Optional[ProcessingTracker] = None
    ):
        self.config = app_config or AppConfig()
        self.remover = remover_service or BackgroundRemoverService(self.config.processing)
        self.processor = image_processor or ImageProcessor(self.config.processing)
        self.file_manager = file_manager or FileManager(self.config)
        self.tracker = tracker or ProcessingTracker(self.config.tracker_file)

    def process_single_image(
        self,
        input_path: Path,
        output_path: Optional[Path] = None,
        bg_color: Optional[str] = None,
        output_format: Optional[str] = None,
        auto_crop: Optional[bool] = None,
        padding_percent: Optional[int] = None
    ) -> Tuple[bool, Optional[Path], Optional[str]]:
        """
        Procesa una única imagen de principio a fin.
        
        Retorna: (Éxito: bool, Ruta de Salida: Path | None, Mensaje de Error: str | None)
        """
        start_time = time.time()
        input_size = input_path.stat().st_size if input_path.exists() else 0
        dest_out = output_path or self.file_manager.determine_output_path(input_path, output_format=output_format)
        
        try:
            if not input_path.exists():
                err = f"[{ErrorCode.FILE_NOT_FOUND.value}] El archivo {input_path} no existe."
                logger.error(err)
                self.tracker.record_job(input_path.name, None, False, time.time() - start_time, error=err)
                return False, None, err

            logger.info(f"Iniciando procesamiento de: {input_path.name} ({format_bytes(input_size)})")

            # 1. Cargar imagen original con Pillow
            try:
                original_img = Image.open(input_path)
                original_img = ImageOps.exif_transpose(original_img)
                dpi = original_img.info.get("dpi")
                dimensions_str = f"{original_img.width}x{original_img.height}"
            except Exception as e:

                err = f"[{ErrorCode.FILE_CORRUPT_OR_UNSUPPORTED.value}] Error al abrir imagen: {e}"
                logger.error(err)
                self.tracker.record_job(input_path.name, None, False, time.time() - start_time, error=err)
                return False, None, err

            # 2. Eliminar fondo con IA (obtiene RGBA)
            rgba_image = self.remover.remove_background(original_img)

            # 3. Aplicar recorte automático / padding si está habilitado
            should_crop = self.config.processing.auto_crop if auto_crop is None else auto_crop
            if should_crop:
                rgba_image = self.processor.auto_crop_and_pad(rgba_image, padding_percent)

            # 4. Superponer sobre fondo blanco sólido y limpiar residuos de fondo
            target_rgba = parse_color_string(bg_color) if bg_color else parse_color_string(self.config.processing.bg_color_raw)
            final_image = self.processor.apply_solid_background(
                rgba_image,
                bg_color=target_rgba,
                original_image=original_img,
                cleanup_residual=True,
            )

            # 5. Guardar resultado final
            saved_path = self.processor.save_image(final_image, dest_out, dpi=dpi)
            duration = time.time() - start_time
            out_size = saved_path.stat().st_size

            logger.info(
                f"[OK] Procesado con exito: {input_path.name} -> {saved_path.name} "
                f"en {duration:.2f}s [{format_bytes(out_size)}]"
            )

            # 6. Registrar métricas en tracker
            self.tracker.record_job(
                input_filename=input_path.name,
                output_filename=saved_path.name,
                success=True,
                duration_sec=duration,
                dimensions=dimensions_str,
                input_size_bytes=input_size,
                output_size_bytes=out_size
            )

            return True, saved_path, None

        except Exception as e:
            duration = time.time() - start_time
            err_msg = f"[{ErrorCode.UNEXPECTED_ERROR.value}] {str(e)}"
            logger.error(f"[ERROR] Fallo procesamiento de {input_path.name}: {e}", exc_info=True)
            self.tracker.record_job(
                input_filename=input_path.name,
                output_filename=None,
                success=False,
                duration_sec=duration,
                input_size_bytes=input_size,
                error=err_msg
            )
            return False, None, err_msg

    def process_batch(
        self,
        images: List[Path],
        output_dir: Optional[Path] = None,
        bg_color: Optional[str] = None,
        max_workers: Optional[int] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Procesa una lista de imágenes en paralelo usando un pool de hilos con límite de lote.
        """
        if not images:
            logger.warning("No hay imágenes para procesar en el lote.")
            return {"total": 0, "successful": 0, "failed": 0, "results": []}

        # Aplicar límite de lote (por defecto 20)
        effective_limit = limit if limit is not None else self.config.processing.batch_limit
        total_found = len(images)

        if total_found > effective_limit:
            logger.warning(
                f"[AVISO] Se encontraron {total_found} imágenes. Aplicando límite de {effective_limit} imágenes para este lote. "
                "(Recordatorio: Entre más imágenes se carguen simultáneamente, mayor es la probabilidad de errores o sobrecarga de memoria)."
            )
            images = images[:effective_limit]

        workers = max_workers or self.config.processing.max_workers
        out_dir = output_dir or self.config.output_dir
        out_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            f"Iniciando procesamiento por lote de {len(images)} imágenes con {workers} hilos "
            f"(Límite configurado: {effective_limit} imágenes)..."
        )
        
        results = []
        successful_count = 0
        failed_count = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_to_img = {
                executor.submit(
                    self.process_single_image,
                    img,
                    self.file_manager.determine_output_path(img, output_dir=out_dir),
                    bg_color
                ): img for img in images
            }

            is_tty = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
            for future in tqdm(as_completed(future_to_img), total=len(images), desc="Procesando imágenes", unit="img", disable=not is_tty):
                img_path = future_to_img[future]
                try:
                    success, out_path, error = future.result()
                    if success:
                        successful_count += 1
                        results.append({"file": str(img_path), "status": "success", "output": str(out_path)})
                    else:
                        failed_count += 1
                        results.append({"file": str(img_path), "status": "failed", "error": error})
                except Exception as exc:
                    failed_count += 1
                    results.append({"file": str(img_path), "status": "failed", "error": str(exc)})

        logger.info(f"Lote finalizado: {successful_count} exitosos, {failed_count} fallidos de {len(images)} totales.")
        return {
            "total": len(images),
            "successful": successful_count,
            "failed": failed_count,
            "results": results
        }
