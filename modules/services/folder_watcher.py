"""Servicio de monitoreo en tiempo real de carpetas (Hot-folder Watcher)."""

import time
import logging
from pathlib import Path
from typing import Optional, Set
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent

from modules.models.config import AppConfig
from modules.services.batch_service import BatchProcessingService
from modules.services.file_manager import FileManager

logger = logging.getLogger(__name__)


class ImageDropHandler(FileSystemEventHandler):
    """Manejador de eventos del sistema de archivos para nuevas imágenes."""

    def __init__(
        self,
        batch_service: BatchProcessingService,
        file_manager: FileManager,
        debounce_seconds: float = 2.0,
        archive_original: bool = True
    ):
        super().__init__()
        self.batch_service = batch_service
        self.file_manager = file_manager
        self.debounce_seconds = debounce_seconds
        self.archive_original = archive_original
        self.processing_files: Set[str] = set()

    def _handle_image_candidate(self, file_path_str: str) -> None:
        file_path = Path(file_path_str)

        # Ignorar directorios o subcarpetas de archivado
        if file_path.is_dir() or any(part in ["processed", "error"] for part in file_path.parts):
            return

        if not self.file_manager.is_supported_image(file_path):
            return

        if str(file_path) in self.processing_files:
            return

        self.processing_files.add(str(file_path))

        try:
            # Esperar a que el archivo termine de escribirse en disco
            logger.info(f"Detectado nuevo archivo: {file_path.name}. Esperando {self.debounce_seconds}s...")
            time.sleep(self.debounce_seconds)

            # Verificar que el archivo todavía exista y tenga tamaño estable
            if not file_path.exists():
                return

            last_size = -1
            stable_checks = 0
            for _ in range(5):
                cur_size = file_path.stat().st_size
                if cur_size == last_size and cur_size > 0:
                    stable_checks += 1
                    if stable_checks >= 2:
                        break
                last_size = cur_size
                time.sleep(0.5)

            # Procesar la imagen a fondo blanco
            success, output_path, error = self.batch_service.process_single_image(file_path)

            # Archivar el original si está habilitado
            if self.archive_original and file_path.exists():
                self.file_manager.archive_original(file_path, success=success)

        except Exception as e:
            logger.error(f"Error procesando evento para {file_path}: {e}")
        finally:
            self.processing_files.discard(str(file_path))

    def on_created(self, event):
        if not event.is_directory:
            self._handle_image_candidate(event.src_path)

    def on_modified(self, event):
        if not event.is_directory:
            self._handle_image_candidate(event.src_path)


class FolderWatcherService:
    """Administra el ciclo de vida del observador de carpetas."""

    def __init__(
        self,
        app_config: Optional[AppConfig] = None,
        batch_service: Optional[BatchProcessingService] = None
    ):
        self.config = app_config or AppConfig()
        self.config.ensure_directories()
        self.batch_service = batch_service or BatchProcessingService(self.config)
        self.file_manager = FileManager(self.config)
        self.observer: Optional[Observer] = None

    def start(self) -> None:
        """Inicia el monitoreo de la carpeta input."""
        input_dir = self.config.input_dir
        logger.info(f"[WATCHER] Iniciando servicio de vigilancia en: {input_dir.resolve()}...")
        logger.info("Copia o arrastra cualquier imagen a esta carpeta para cambiar automaticamente su fondo a blanco.")

        handler = ImageDropHandler(
            batch_service=self.batch_service,
            file_manager=self.file_manager,
            debounce_seconds=self.config.watcher.debounce_seconds,
            archive_original=self.config.watcher.archive_original
        )

        self.observer = Observer()
        self.observer.schedule(handler, str(input_dir), recursive=False)
        self.observer.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Deteniendo servicio de vigilancia...")
            self.stop()

    def stop(self) -> None:
        """Detiene el observador de carpetas de forma segura."""
        if self.observer and self.observer.is_alive():
            self.observer.stop()
            self.observer.join()
            logger.info("Servicio de vigilancia detenido.")
