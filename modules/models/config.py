"""Configuración centralizada y tipada para background remover con persistencia en AppData."""

import os
from pathlib import Path
from typing import Tuple, Optional
from dataclasses import dataclass, field

# Cargar variables de entorno si .env existe (modo desarrollo opcional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

from modules.models.settings_manager import settings_manager


@dataclass
class ProcessingConfig:
    """Configuración del pipeline de remoción y composición."""
    # Fondo por defecto: blanco puro
    bg_color_raw: str = field(default_factory=lambda: settings_manager.get("bg_color", os.getenv("BG_COLOR", "255,255,255")))
    bg_color_rgba: Tuple[int, int, int, int] = field(default_factory=lambda: (255, 255, 255, 255))
    output_format: str = field(default_factory=lambda: settings_manager.get("output_format", os.getenv("OUTPUT_FORMAT", "JPEG")).upper())
    output_quality: int = field(default_factory=lambda: int(settings_manager.get("output_quality", os.getenv("OUTPUT_QUALITY", "95"))))
    
    # Configuración de modelo IA (por defecto auto)
    model_name: str = field(default_factory=lambda: settings_manager.get("model_name", os.getenv("DEFAULT_MODEL", "auto")))
    alpha_matting: bool = field(default_factory=lambda: bool(settings_manager.get("alpha_matting", os.getenv("ALPHA_MATTING", "false").lower() == "true")))
    alpha_matting_fg_threshold: int = int(os.getenv("ALPHA_MATTING_FOREGROUND_THRESHOLD", "240"))
    alpha_matting_bg_threshold: int = int(os.getenv("ALPHA_MATTING_BACKGROUND_THRESHOLD", "10"))
    alpha_matting_erode_size: int = int(os.getenv("ALPHA_MATTING_ERODE_SIZE", "10"))
    
    # Ajustes geométricos
    auto_crop: bool = field(default_factory=lambda: bool(settings_manager.get("auto_crop", os.getenv("AUTO_CROP", "false").lower() == "true")))
    padding_percent: int = int(os.getenv("PADDING_PERCENT", "5"))
    
    # Límites y Concurrencia
    batch_limit: int = field(default_factory=lambda: int(settings_manager.get("batch_limit", os.getenv("BATCH_LIMIT", "20"))))
    max_batch_limit: int = int(os.getenv("MAX_BATCH_LIMIT", "20"))
    max_file_size_mb: int = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
    timeout_seconds: int = int(os.getenv("TIMEOUT_SECONDS", "60"))
    max_workers: int = int(os.getenv("MAX_WORKERS", "4"))


@dataclass
class WatcherConfig:
    """Configuración para el modo vigilante de carpetas (hot-folder)."""
    enabled: bool = False
    debounce_seconds: float = float(os.getenv("WATCHER_DEBOUNCE_SECONDS", "2.0"))
    archive_original: bool = os.getenv("ARCHIVE_ORIGINAL", "true").lower() == "true"


@dataclass
class AppConfig:
    """Configuración global de la aplicación."""
    input_dir: Path = field(default_factory=lambda: Path(os.getenv("INPUT_DIR", "input")))
    output_dir: Path = field(
        default_factory=lambda: Path(settings_manager.get("output_dir")) if settings_manager.get("output_dir") else Path(os.getenv("OUTPUT_DIR", "output"))
    )
    processed_dir: Path = Path(os.getenv("PROCESSED_DIR", "input/processed"))
    error_dir: Path = Path(os.getenv("ERROR_DIR", "input/error"))
    logs_dir: Path = field(
        default_factory=lambda: Path(os.getenv("LOGS_DIR")) if os.getenv("LOGS_DIR") else settings_manager.app_dir / "logs"
    )
    tracker_file: Path = field(
        default_factory=lambda: Path(os.getenv("TRACKER_FILE")) if os.getenv("TRACKER_FILE") else settings_manager.app_dir / "processing_tracker.json"
    )
    cleanup_days: int = int(os.getenv("CLEANUP_DAYS", "30"))
    
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)
    watcher: WatcherConfig = field(default_factory=WatcherConfig)
    
    def ensure_directories(self) -> None:
        """Crea directorios para modos que requieren carpetas por defecto (ej. hot-folder watcher)."""
        for directory in [self.input_dir, self.output_dir, self.processed_dir, self.error_dir, self.logs_dir]:
            directory.mkdir(parents=True, exist_ok=True)


# Instancia singleton de configuración
config = AppConfig()
