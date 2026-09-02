"""
Punto de entrada principal para Background Remover Pro.
Soporta splash screen nativo de PyInstaller (bootloader) y splash screen ligero de Tkinter
para garantizar respuesta visual inmediata (< 50 ms) al abrir la aplicación.
"""

import sys
import time
import threading
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


def _launch_gui_with_splash():
    """Muestra el splash screen inmediatamente (< 50ms) y carga la GUI de forma asíncrona."""
    pyi_splash = None
    try:
        import pyi_splash as _ps
        if hasattr(_ps, "is_alive") and _ps.is_alive():
            pyi_splash = _ps
    except Exception:
        pyi_splash = None

    tk_splash = None
    if pyi_splash is None:
        from modules.ui.splash_screen import SplashScreen
        tk_splash = SplashScreen()

    def set_splash_progress(fraction: float, text: str):
        pct = int(round(fraction * 100))
        if pyi_splash is not None:
            try:
                pyi_splash.update_text(f"{text} ({pct}%)")
            except Exception:
                pass
        elif tk_splash is not None:
            tk_splash.set_progress(fraction, text)

    app_target_fn = None
    app_error = None
    load_completed = False

    def background_loader():
        nonlocal app_target_fn, app_error, load_completed
        try:
            # Fase 1: Servicios del sistema y logs
            set_splash_progress(0.20, "Iniciando servicios del sistema...")
            time.sleep(0.35)
            from modules.core.app import setup_logging
            setup_logging()

            # Fase 2: Configuración y utilidades de archivos
            set_splash_progress(0.45, "Cargando motor de Inteligencia Artificial...")
            time.sleep(0.40)
            from modules.models.config import config
            from modules.services.file_manager import FileManager

            # Fase 3: Motor ONNX y modelos de visión
            set_splash_progress(0.70, "Inicializando modelos de visión y ONNX...")
            time.sleep(0.45)
            from modules.services.batch_service import BatchProcessingService

            # Fase 4: Componentes de interfaz gráfica
            set_splash_progress(0.90, "Preparando interfaz gráfica...")
            time.sleep(0.40)
            from modules.ui.app_gui import launch_gui
            app_target_fn = launch_gui

            # Fase 5: Conclusión
            set_splash_progress(1.00, "¡Listo! Iniciando Background Remover...")
            time.sleep(0.40)
            load_completed = True
        except Exception as e:
            app_error = e
            load_completed = True

    loader_thread = threading.Thread(target=background_loader, daemon=True)
    loader_thread.start()

    if pyi_splash is not None:
        # El splash nativo de PyInstaller se mostró desde el segundo 0 (bootloader C)
        while not load_completed or loader_thread.is_alive():
            time.sleep(0.05)
        try:
            pyi_splash.close()
        except Exception:
            pass
        if app_error:
            import tkinter.messagebox as mb
            mb.showerror("Error al Iniciar", f"Ocurrió un error al cargar la aplicación:\n{app_error}")
            sys.exit(1)
        if app_target_fn:
            app_target_fn()
    else:
        # Modo Tkinter Splash (ejecución directa o entornos sin bootloader splash)
        def check_tk_loading():
            if load_completed and not loader_thread.is_alive():
                if tk_splash._current_progress < 0.98:
                    tk_splash._target_progress = 1.0
                    tk_splash._current_progress = 1.0
                    tk_splash._percent_label.configure(text="100%")
                    tk_splash._status_label.configure(text="¡Listo! Iniciando Background Remover...")
                    tk_splash._root.update_idletasks()
                    tk_splash._root.after(250, check_tk_loading)
                    return

                tk_splash.close()
                if app_error:
                    import tkinter.messagebox as mb
                    mb.showerror("Error al Iniciar", f"Ocurrió un error al cargar la aplicación:\n{app_error}")
                    sys.exit(1)
                if app_target_fn:
                    app_target_fn()
            else:
                if tk_splash._alive:
                    tk_splash._root.after(30, check_tk_loading)

        tk_splash._root.after(30, check_tk_loading)
        tk_splash.run()


def main():
    if _is_gui_mode:
        _launch_gui_with_splash()
        return 0
    else:
        try:
            import pyi_splash
            pyi_splash.close()
        except Exception:
            pass
        from modules.core.app import main as cli_main
        return cli_main()


if __name__ == "__main__":
    sys.exit(main())


