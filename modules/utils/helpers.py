"""Módulo de utilidades y funciones auxiliares."""

import re
import time
import logging
from typing import Tuple, Optional, Callable, Any
from functools import wraps

logger = logging.getLogger(__name__)


def register_heif_support() -> bool:
    """Registra el opener de pillow-heif para soporte transparente de archivos .heic y .heif."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        logger.debug("Soporte HEIC/HEIF registrado exitosamente con pillow-heif.")
        return True
    except ImportError:
        logger.debug("pillow-heif no está instalado; HEIC/HEIF deshabilitado.")
        return False
    except Exception as e:
        logger.warning(f"No se pudo registrar soporte HEIC/HEIF: {e}")
        return False


# Registrar automáticamente al importar el módulo
register_heif_support()



def parse_color_string(color_str: str) -> Tuple[int, int, int, int]:
    """
    Parsea una cadena de texto a una tupla RGBA (r, g, b, a).
    
    Soporta:
      - Nombres: 'white', 'black', 'transparent', 'red', etc.
      - Hex: '#FFFFFF', '#FFF', 'FFFFFF'
      - RGB / RGBA: '255,255,255' o '255,255,255,255'
    """
    if not color_str:
        return (255, 255, 255, 255)
        
    s = color_str.strip().lower()
    
    # Nombres comunes
    named_colors = {
        "white": (255, 255, 255, 255),
        "blanco": (255, 255, 255, 255),
        "transparent": (0, 0, 0, 0),
        "transparente": (0, 0, 0, 0),
        "none": (0, 0, 0, 0),
        "black": (0, 0, 0, 255),
        "negro": (0, 0, 0, 255),
        "gray": (128, 128, 128, 255),
        "grey": (128, 128, 128, 255),
        "gris": (128, 128, 128, 255),
        "lightgray": (240, 240, 240, 255),
        "red": (255, 0, 0, 255),
        "green": (0, 255, 0, 255),
        "blue": (0, 0, 255, 255)
    }
    if s in named_colors:
        return named_colors[s]
        
    # Hexadecimal
    if s.startswith("#") or (len(s) in (3, 6, 8) and all(c in "0123456789abcdef" for c in s)):
        clean_hex = s.lstrip("#")
        if len(clean_hex) == 3:
            clean_hex = "".join([c*2 for c in clean_hex])
        if len(clean_hex) == 6:
            r = int(clean_hex[0:2], 16)
            g = int(clean_hex[2:4], 16)
            b = int(clean_hex[4:6], 16)
            return (r, g, b, 255)
        elif len(clean_hex) == 8:
            r = int(clean_hex[0:2], 16)
            g = int(clean_hex[2:4], 16)
            b = int(clean_hex[4:6], 16)
            a = int(clean_hex[6:8], 16)
            return (r, g, b, a)
            
    # Formato numérico separado por comas / espacios
    parts = re.split(r'[,;\s]+', s.strip('()[]'))
    nums = [int(p) for p in parts if p.isdigit()]
    if len(nums) == 3:
        return (nums[0], nums[1], nums[2], 255)
    elif len(nums) >= 4:
        return (nums[0], nums[1], nums[2], nums[3])
        
    logger.warning(f"No se pudo parsear el color '{color_str}', usando blanco por defecto.")
    return (255, 255, 255, 255)


def format_bytes(size_in_bytes: int) -> str:
    """Convierte bytes a un formato legible (KB, MB, GB)."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024.0:
            return f"{size_in_bytes:.1f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.1f} TB"


class CircuitBreakerOpenException(Exception):
    """Excepción lanzada cuando el circuito está abierto."""
    pass


class CircuitBreaker:
    """Implementación de patrón Circuit Breaker para protección ante fallos consecutivos."""
    def __init__(self, failure_threshold: int = 3, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF-OPEN
        self.last_state_change = time.time()

    def record_success(self):
        self.failure_count = 0
        self.state = "CLOSED"

    def record_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.state = "OPEN"
            self.last_state_change = time.time()
            logger.error(f"CircuitBreaker ABIERTO tras {self.failure_count} fallos consecutivos.")

    def can_execute(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.last_state_change > self.recovery_timeout:
                self.state = "HALF-OPEN"
                logger.info("CircuitBreaker en estado HALF-OPEN (probando recuperación).")
                return True
            return False
        if self.state == "HALF-OPEN":
            return True
        return False


def retry(max_attempts: int = 3, delay: float = 1.0, exceptions=(Exception,)):
    """Decorador para reintentar funciones con retardo exponencial simple."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            attempts = 0
            current_delay = delay
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    attempts += 1
                    if attempts >= max_attempts:
                        logger.error(f"Función {func.__name__} falló tras {max_attempts} intentos: {e}")
                        raise
                    logger.warning(f"Reintentando {func.__name__} (intento {attempts}/{max_attempts}) en {current_delay}s debido a: {e}")
                    time.sleep(current_delay)
                    current_delay *= 2
        return wrapper
    return decorator
