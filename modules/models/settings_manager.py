"""
Gestor de configuraciones y preferencias de usuario persistentes en AppData.
Permite que la app recuerde las preferencias del usuario (formato, modelo, rutas, limite)
entre sesiones sin depender de archivos .env cuando se compila como ejecutable (.exe).
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger(__name__)

APP_NAME = "BackgroundRemover"


def get_appdata_dir() -> Path:
    """Obtiene el directorio de datos de la aplicacion en el sistema del usuario."""
    if sys.platform == "win32":
        app_data = os.getenv("APPDATA")
        if app_data:
            base_dir = Path(app_data)
        else:
            base_dir = Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        base_dir = Path.home() / "Library" / "Application Support"
    else:
        base_dir = Path.home() / ".config"

    app_dir = base_dir / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


class SettingsManager:
    """Carga y guarda de forma persistente las preferencias en AppData/BackgroundRemover/settings.json."""

    DEFAULT_SETTINGS: Dict[str, Any] = {
        "output_dir": "",
        "bg_color": "white",
        "bg_color_hex": "#FFFFFF",
        "output_format": "JPEG",
        "output_quality": 95,
        "model_name": "auto",
        "batch_limit": 20,
        "auto_crop": False,
        "alpha_matting": False,
        "theme": "dark",
    }

    def __init__(self, settings_file: Path = None):
        self.app_dir = get_appdata_dir()
        self.settings_file = settings_file or (self.app_dir / "settings.json")
        self.settings: Dict[str, Any] = dict(self.DEFAULT_SETTINGS)
        self.settings = self.load_settings()

    def load_settings(self) -> Dict[str, Any]:
        """Carga las preferencias desde el archivo JSON o crea las predeterminadas."""
        settings = dict(self.DEFAULT_SETTINGS)
        if self.settings_file.exists():
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, dict):
                        settings.update(saved)
                logger.info(f"Preferencias de usuario cargadas desde: {self.settings_file}")
            except Exception as e:
                logger.warning(f"No se pudo leer {self.settings_file}: {e}. Usando valores por defecto.")
        else:
            self.save_settings(settings)
        return settings

    def save_settings(self, new_settings: Dict[str, Any] = None) -> bool:
        """Guarda las preferencias en disco en formato JSON."""
        if new_settings:
            self.settings.update(new_settings)
        try:
            temp_file = self.settings_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self.settings, f, indent=2, ensure_ascii=False)
            temp_file.replace(self.settings_file)
            logger.debug(f"Preferencias guardadas exitosamente en {self.settings_file}")
            return True
        except Exception as e:
            logger.error(f"Error al guardar preferencias en {self.settings_file}: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Obtiene un valor de configuracion."""
        return self.settings.get(key, default if default is not None else self.DEFAULT_SETTINGS.get(key))

    def set(self, key: str, value: Any) -> None:
        """Establece y persiste una configuracion individual."""
        self.settings[key] = value
        self.save_settings()


# Instancia singleton
settings_manager = SettingsManager()
