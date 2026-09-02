"""Servicio para gestión, filtrado y archivo seguro de imágenes en el sistema."""

import shutil
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime

from modules.models.config import AppConfig
from modules.utils.helpers import register_heif_support

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".heic", ".heif"}


class FileManager:
    """Administra archivos de entrada, salida, movimientos post-proceso y limpieza."""

    def __init__(self, app_config: Optional[AppConfig] = None):
        register_heif_support()
        self.config = app_config or AppConfig()


    def is_supported_image(self, file_path: Path) -> bool:
        """Comprueba si la extensión del archivo es un formato de imagen soportado."""
        return file_path.is_file() and file_path.suffix.lower() in SUPPORTED_EXTENSIONS

    def get_input_images(self, source_dir: Optional[Path] = None, recursive: bool = False) -> List[Path]:
        """Obtiene todas las imágenes válidas en el directorio indicado."""
        directory = source_dir or self.config.input_dir
        if not directory.exists():
            return []

        pattern = "**/*" if recursive else "*"
        images = []
        for p in directory.glob(pattern):
            # Ignorar subdirectorios de archivado (processed, error)
            if any(part in ["processed", "error", ".git", ".vscode"] for part in p.parts):
                continue
            if self.is_supported_image(p):
                images.append(p)
        return sorted(images)

    def determine_output_path(
        self,
        input_path: Path,
        output_dir: Optional[Path] = None,
        output_format: Optional[str] = None
    ) -> Path:
        """Calcula la ruta de salida con el nombre y extensión correspondientes."""
        out_dir = output_dir or self.config.output_dir
        fmt = (output_format or self.config.processing.output_format).lower()
        
        # Mapear formato a extensión
        ext_map = {"jpeg": ".jpg", "jpg": ".jpg", "png": ".png", "webp": ".webp"}
        target_ext = ext_map.get(fmt, f".{fmt}")
        
        filename = f"{input_path.stem}_white_bg{target_ext}"
        return out_dir / filename

    def archive_original(self, input_path: Path, success: bool = True) -> Optional[Path]:
        """Mueve la imagen de entrada a la carpeta processed/ o error/."""
        target_folder = self.config.processed_dir if success else self.config.error_dir
        target_folder.mkdir(parents=True, exist_ok=True)
        
        # Evitar sobreescritura añadiendo timestamp si ya existe
        dest_path = target_folder / input_path.name
        if dest_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            dest_path = target_folder / f"{input_path.stem}_{timestamp}{input_path.suffix}"

        try:
            shutil.move(str(input_path), str(dest_path))
            logger.debug(f"Archivo original movido a: {dest_path}")
            return dest_path
        except Exception as e:
            logger.error(f"Error moviendo archivo {input_path} a {dest_path}: {e}")
            return None
