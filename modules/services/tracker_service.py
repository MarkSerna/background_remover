"""Servicio de seguimiento y métricas de procesamiento persistente."""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from datetime import datetime

from modules.models.config import config

logger = logging.getLogger(__name__)


class ProcessingTracker:
    """Registra y persiste el histórico de imágenes procesadas y métricas de rendimiento."""

    def __init__(self, tracker_file: Optional[Path] = None):
        self.file_path = tracker_file or config.tracker_file
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.file_path.exists():
            return {
                "summary": {
                    "total_processed": 0,
                    "successful": 0,
                    "failed": 0,
                    "total_duration_sec": 0.0
                },
                "history": []
            }
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando tracker desde {self.file_path}: {e}")
            return {"summary": {"total_processed": 0, "successful": 0, "failed": 0, "total_duration_sec": 0.0}, "history": []}

    def _save(self) -> None:
        try:
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Error guardando tracker en {self.file_path}: {e}")

    def record_job(
        self,
        input_filename: str,
        output_filename: Optional[str],
        success: bool,
        duration_sec: float,
        dimensions: Optional[str] = None,
        input_size_bytes: int = 0,
        output_size_bytes: int = 0,
        error: Optional[str] = None
    ) -> None:
        """Registra el resultado del procesamiento de una imagen."""
        self.data["summary"]["total_processed"] += 1
        if success:
            self.data["summary"]["successful"] += 1
        else:
            self.data["summary"]["failed"] += 1
            
        self.data["summary"]["total_duration_sec"] += round(duration_sec, 2)

        record = {
            "timestamp": datetime.now().isoformat(),
            "input_file": input_filename,
            "output_file": output_filename,
            "success": success,
            "duration_sec": round(duration_sec, 2),
            "dimensions": dimensions,
            "input_size_bytes": input_size_bytes,
            "output_size_bytes": output_size_bytes,
            "error": error
        }

        # Mantener últimos 1000 registros en histórico
        self.data["history"].append(record)
        if len(self.data["history"]) > 1000:
            self.data["history"] = self.data["history"][-1000:]

        self._save()

    def get_summary(self) -> Dict[str, Any]:
        """Retorna el resumen de métricas."""
        return self.data.get("summary", {})
