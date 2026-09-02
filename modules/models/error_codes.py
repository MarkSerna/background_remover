"""Definición y catálogo de códigos de error estructurados."""

from enum import Enum
from dataclasses import dataclass
from typing import Optional


class ErrorSeverity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass
class ErrorDetail:
    code: str
    description: str
    severity: ErrorSeverity
    suggested_action: str


class ErrorCode(Enum):
    # Errores de Configuración (1000-1099)
    CONFIG_INVALID_COLOR = "ERR_1001"
    CONFIG_INVALID_MODEL = "ERR_1002"
    CONFIG_INVALID_FORMAT = "ERR_1003"
    CONFIG_INVALID_DIR = "ERR_1004"

    # Errores de Archivo e I/O (1100-1199)
    FILE_NOT_FOUND = "ERR_1101"
    FILE_CORRUPT_OR_UNSUPPORTED = "ERR_1102"
    FILE_TOO_LARGE = "ERR_1103"
    FILE_PERMISSION_DENIED = "ERR_1104"
    FILE_SAVE_FAILED = "ERR_1105"
    BATCH_LIMIT_EXCEEDED = "ERR_1106"

    # Errores de Motor IA y Procesamiento (1200-1299)
    MODEL_LOAD_FAILED = "ERR_1201"
    INFERENCE_FAILED = "ERR_1202"
    INFERENCE_TIMEOUT = "ERR_1203"
    COMPOSITION_FAILED = "ERR_1204"
    ALPHA_MATTING_FAILED = "ERR_1205"

    # Errores de Vigilante y Concurrencia (1300-1399)
    WATCHER_START_FAILED = "ERR_1301"
    WATCHER_EVENT_FAILED = "ERR_1302"
    BATCH_WORKER_TIMEOUT = "ERR_1303"

    # Errores Generales (1900-1999)
    SYSTEM_OUT_OF_MEMORY = "ERR_1901"
    UNEXPECTED_ERROR = "ERR_1999"


ERROR_CATALOG = {
    ErrorCode.CONFIG_INVALID_COLOR: ErrorDetail(
        code="ERR_1001",
        description="El formato del color de fondo no es válido (use 'white', '#FFFFFF' o '255,255,255')",
        severity=ErrorSeverity.HIGH,
        suggested_action="Verifique la variable BG_COLOR en su archivo .env o en los argumentos CLI."
    ),
    ErrorCode.CONFIG_INVALID_MODEL: ErrorDetail(
        code="ERR_1002",
        description="El modelo de IA solicitado no es reconocido o compatible",
        severity=ErrorSeverity.HIGH,
        suggested_action="Seleccione un modelo válido como u2net, u2netp o isnet-general-use."
    ),
    ErrorCode.CONFIG_INVALID_FORMAT: ErrorDetail(
        code="ERR_1003",
        description="Formato de salida no soportado",
        severity=ErrorSeverity.MEDIUM,
        suggested_action="Use JPEG, PNG o WEBP."
    ),
    ErrorCode.FILE_NOT_FOUND: ErrorDetail(
        code="ERR_1101",
        description="El archivo de imagen especificado no existe",
        severity=ErrorSeverity.HIGH,
        suggested_action="Verifique la ruta de entrada provista."
    ),
    ErrorCode.FILE_CORRUPT_OR_UNSUPPORTED: ErrorDetail(
        code="ERR_1102",
        description="La imagen está dañada o no tiene un formato compatible",
        severity=ErrorSeverity.HIGH,
        suggested_action="Asegúrese de que el archivo sea una imagen válida (JPG, PNG, WEBP, BMP)."
    ),
    ErrorCode.FILE_TOO_LARGE: ErrorDetail(
        code="ERR_1103",
        description="El archivo excede el tamaño máximo configurado",
        severity=ErrorSeverity.MEDIUM,
        suggested_action="Reduzca el tamaño de la imagen o aumente MAX_FILE_SIZE_MB en .env."
    ),
    ErrorCode.MODEL_LOAD_FAILED: ErrorDetail(
        code="ERR_1201",
        description="Fallo al descargar o inicializar el modelo ONNX de rembg",
        severity=ErrorSeverity.CRITICAL,
        suggested_action="Compruebe su conexión a internet (para la primera descarga) o permisos en ~/.u2net."
    ),
    ErrorCode.INFERENCE_FAILED: ErrorDetail(
        code="ERR_1202",
        description="Error durante la ejecución del recorte de fondo por IA",
        severity=ErrorSeverity.HIGH,
        suggested_action="Revise el archivo log para más detalles del stacktrace."
    ),
    ErrorCode.COMPOSITION_FAILED: ErrorDetail(
        code="ERR_1204",
        description="Error al componer el sujeto sobre el fondo blanco",
        severity=ErrorSeverity.HIGH,
        suggested_action="Verifique la compatibilidad de canales y dimensiones con Pillow."
    ),
    ErrorCode.BATCH_LIMIT_EXCEEDED: ErrorDetail(
        code="ERR_1106",
        description="El lote excede el límite máximo de imágenes permitido (máximo 20)",
        severity=ErrorSeverity.MEDIUM,
        suggested_action="Divida las imágenes en lotes de hasta 20 imágenes para evitar errores o sobrecarga de memoria."
    ),
}


def get_error_detail(error_code: ErrorCode) -> Optional[ErrorDetail]:
    """Obtiene el detalle completo de un código de error."""
    return ERROR_CATALOG.get(error_code)
