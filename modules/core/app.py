"""Orquestador principal de la aplicación Background Remover."""

import os
import sys
import time
import argparse
import logging
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional

from modules.models.config import config, AppConfig
from modules.models.error_codes import ErrorCode
from modules.services.batch_service import BatchProcessingService
from modules.services.folder_watcher import FolderWatcherService
from modules.services.file_manager import FileManager
from modules.services.tracker_service import ProcessingTracker


class _NullStream:
    """Stream nulo para evitar errores cuando la aplicación corre sin consola (PyInstaller --noconsole)."""
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


def setup_logging() -> None:
    """Configura el sistema de logging rotativo y salida en consola de forma segura."""
    if hasattr(sys.stdout, "reconfigure") and not isinstance(sys.stdout, _NullStream):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if hasattr(sys.stderr, "reconfigure") and not isinstance(sys.stderr, _NullStream):
        try:
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    log_dir = Path(config.logs_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    
    formatter = logging.Formatter(
        '%(asctime)s - [%(levelname)s] - %(name)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler para archivo rotativo de 10 MB (hasta 5 backups)
    file_handler = RotatingFileHandler(
        log_dir / "remover_app.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Evitar handlers duplicados si se llama varias veces
    if not root_logger.handlers:
        root_logger.addHandler(file_handler)
        # Solo agregar handler de consola si stdout no es nulo
        if sys.stdout is not None and not isinstance(sys.stdout, _NullStream):
            try:
                console_handler = logging.StreamHandler(sys.stdout)
                console_handler.setFormatter(formatter)
                root_logger.addHandler(console_handler)
            except Exception:
                pass
    
    # Suprimir logs verbosos de librerías externas
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('watchdog').setLevel(logging.INFO)
    logging.getLogger('onnxruntime').setLevel(logging.WARNING)


class BackgroundRemoverApp:
    """Clase principal que maneja el ciclo de vida de la aplicación."""

    def __init__(self):
        self.logger = logging.getLogger(self.__class__.__name__)
        self.file_manager = FileManager(config)
        self.tracker = ProcessingTracker(config.tracker_file)
        self.batch_service = BatchProcessingService(
            app_config=config,
            file_manager=self.file_manager,
            tracker=self.tracker
        )

    def print_banner(self) -> None:
        try:
            print("""
============================================================
       [BACKGROUND REMOVER] - FONDO BLANCO INTELIGENTE
                  Powered by Altikore
============================================================
""")
        except Exception:
            pass

    def run_cli(self, args: argparse.Namespace, splash=None) -> int:
        """Procesa los argumentos provistos desde la línea de comandos."""
        # 0. Si no se pasaron argumentos en consola o se especifico --gui, abrir la GUI por defecto
        no_cli_args = len(sys.argv) == 1
        if (no_cli_args or getattr(args, "gui", False)) and not getattr(args, "cli", False):
            from modules.ui.app_gui import launch_gui
            if splash is not None:
                splash.close()   # cerrar splash antes de abrir la interfaz gráfica Flet
            launch_gui()
            return 0

        self.print_banner()

        # 1. Modo Estadísticas
        if args.stats:
            summary = self.tracker.get_summary()
            print("\n[RESUMEN DE PROCESAMIENTO]")
            print(f"  * Total procesadas: {summary.get('total_processed', 0)}")
            print(f"  * Exitosas:         {summary.get('successful', 0)}")
            print(f"  * Fallidas:         {summary.get('failed', 0)}")
            print(f"  * Tiempo total:     {summary.get('total_duration_sec', 0):.2f}s\n")
            return 0

        # 2. Modo Watcher (Vigilante de Carpeta)
        if args.watch:
            watcher = FolderWatcherService(config, self.batch_service)
            watcher.start()
            return 0

        # Sobrescribir configuraciones si vienen por CLI
        if args.color:
            config.processing.bg_color_raw = args.color
        if args.format:
            config.processing.output_format = args.format.upper()
        if args.model:
            config.processing.model_name = args.model
        if args.alpha_matting:
            config.processing.alpha_matting = True
        if args.auto_crop:
            config.processing.auto_crop = True

        input_target = Path(args.input) if args.input else config.input_dir

        # 3. Modo Archivo Único
        if input_target.is_file():
            out_target = Path(args.output) if args.output else None
            success, out_path, err = self.batch_service.process_single_image(
                input_path=input_target,
                output_path=out_target,
                bg_color=args.color,
                output_format=args.format,
                auto_crop=args.auto_crop
            )
            if success:
                print(f"\n[OK] Imagen generada con fondo blanco en: {out_path}\n")
                return 0
            else:
                print(f"\n[ERROR] Error al procesar imagen: {err}\n")
                return 1

        # 4. Modo Directorio / Batch
        elif input_target.is_dir():
            images = self.file_manager.get_input_images(input_target, recursive=args.recursive)
            if not images:
                self.logger.warning(f"No se encontraron imágenes compatibles en: {input_target.resolve()}")
                print(f"\n[AVISO] No hay imágenes para procesar en '{input_target}'. Coloca imágenes JPG/PNG/WEBP/HEIC allí.\n")
                return 0


            out_dir = Path(args.output) if args.output else config.output_dir
            results = self.batch_service.process_batch(
                images=images,
                output_dir=out_dir,
                bg_color=args.color,
                max_workers=args.workers,
                limit=args.limit
            )

            print("\n============================================================")
            print(f"Proceso por lotes finalizado:")
            print(f"   * Exitosas: {results['successful']}/{results['total']}")
            print(f"   * Fallidas: {results['failed']}/{results['total']}")
            print(f"   * Carpeta de salida: {out_dir.resolve()}")
            print("   * [NOTA]: Entre más imágenes se procesen simultáneamente,")
            print("             mayor es la probabilidad de errores de memoria o I/O.")
            print("============================================================\n")
            return 0 if results['failed'] == 0 else 1

        else:
            self.logger.error(f"La ruta especificada no existe: {input_target}")
            print(f"[ERROR] La ruta especificada no existe: {input_target}")
            return 1


def parse_arguments() -> argparse.Namespace:
    """Configura y parsea los argumentos de línea de comandos."""
    parser = argparse.ArgumentParser(
        description="Background Remover - Remoción de fondo y sustitución por blanco puro."
    )
    
    parser.add_argument("-g", "--gui", action="store_true", help="Abre la interfaz gráfica de usuario interactiva (por defecto si no hay argumentos).")
    parser.add_argument("--cli", action="store_true", help="Fuerza la ejecución en modo consola sin abrir la interfaz gráfica.")
    parser.add_argument("-i", "--input", type=str, help="Ruta de la imagen o directorio de entrada.")
    parser.add_argument("-o", "--output", type=str, help="Ruta de la imagen o directorio de salida.")
    parser.add_argument("-l", "--limit", type=int, default=config.processing.batch_limit, help="Límite máximo de imágenes a procesar por lote (por defecto 20).")
    parser.add_argument("-c", "--color", type=str, help="Color de fondo (ej: 'white', '#FFFFFF', '255,255,255', 'transparent'). Por defecto blanco.")
    parser.add_argument("-f", "--format", type=str, choices=["JPEG", "PNG", "WEBP", "jpeg", "png", "webp"], help="Formato de salida.")
    parser.add_argument("-m", "--model", type=str, help="Modelo IA de rembg (ej: u2net, isnet-general-use).")
    parser.add_argument("-w", "--watch", action="store_true", help="Inicia en modo vigilante monitoreando la carpeta input/.")
    parser.add_argument("-r", "--recursive", action="store_true", help="Buscar imágenes recursivamente en subdirectorios.")
    parser.add_argument("--workers", type=int, help="Número de hilos concurrentes para procesamiento en lote.")
    parser.add_argument("--auto-crop", action="store_true", help="Recorta los bordes sobrantes centrando el sujeto.")
    parser.add_argument("--alpha-matting", action="store_true", help="Habilita refinamiento de bordes alpha matting para detalles finos.")
    parser.add_argument("--stats", action="store_true", help="Muestra el histórico y métricas de procesamiento acumuladas.")

    return parser.parse_args()


def main(splash=None) -> int:
    """Función de entrada principal."""
    setup_logging()
    args = parse_arguments()

    # Si no se proporcionan argumentos o se pasa --gui (y no --cli), abrir la interfaz grafica
    no_cli_args = len(sys.argv) == 1
    if (no_cli_args or getattr(args, "gui", False)) and not getattr(args, "cli", False):
        from modules.ui.app_gui import launch_gui
        if splash is not None:
            splash.close()   # cerrar splash antes de mostrar la interfaz gráfica Flet
        launch_gui()
        return 0

    # Modo CLI: cerrar splash si estaba activo (caso inusual)
    if splash is not None:
        splash.close()

    app = BackgroundRemoverApp()
    return app.run_cli(args, splash=splash)
