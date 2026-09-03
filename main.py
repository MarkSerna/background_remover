"""
Punto de entrada principal para Background Remover.
Soporta modo de interfaz gráfica moderna con Flet y modo de línea de comandos (CLI).
"""

import sys
from pathlib import Path

# Stream nulo para evitar fallos 'NoneType object has no attribute write' en modo windowed/noconsole
class _NullStream:
    def write(self, *args, **kwargs):
        pass
    def flush(self, *args, **kwargs):
        pass
    def isatty(self):
        return False

if sys.stdout is None:
    sys.stdout = _NullStream()
if sys.stderr is None:
    sys.stderr = _NullStream()

# Asegurar que el directorio raíz esté en sys.path para imports limpios
sys.path.insert(0, str(Path(__file__).parent))

# Detectar modo de ejecución (GUI por defecto si no hay argumentos o se pasa --gui)
_is_cli_explicit = "--cli" in sys.argv or any(arg in sys.argv for arg in ["-i", "--input", "-w", "--watch", "--stats"])
_is_gui_mode = not _is_cli_explicit or "--gui" in sys.argv


def _close_pyi_splash():
    """Cierra el splash nativo de PyInstaller si está activo."""
    try:
        import pyi_splash
        if hasattr(pyi_splash, "is_alive") and pyi_splash.is_alive():
            pyi_splash.close()
    except Exception:
        pass


def main():
    if _is_gui_mode:
        from modules.core.app import setup_logging
        setup_logging()
        _close_pyi_splash()
        from modules.ui.app_gui import launch_gui
        launch_gui()
        return 0
    else:
        _close_pyi_splash()
        from modules.core.app import main as cli_main
        return cli_main()


if __name__ == "__main__":
    sys.exit(main())
