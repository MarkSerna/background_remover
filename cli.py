"""
CLI Avanzado para Background Remover: Layered Segmentation & Studio Compositing.
Uso:
  python cli.py -i foto.jpg -o resultado.png --mode studio --bg white
  python cli.py -i ./input/ -o ./output/ --mode studio --bg transparent --prompt "product"
"""

import argparse
import sys
import logging
from pathlib import Path
from typing import List

from PIL import Image

from pipelines.standard import StandardPipeline
from pipelines.studio_layered import StudioLayeredPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [%(levelname)s] - %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("cli")

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".heic", ".heif"}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Background Remover Pro — Layered Segmentation & Studio Compositing Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-i", "--input",
        required=True,
        type=str,
        help="Ruta de la imagen de entrada o carpeta con imágenes.",
    )
    parser.add_argument(
        "-o", "--output",
        default=None,
        type=str,
        help="Ruta del archivo o carpeta de salida (por defecto ./output/).",
    )
    parser.add_argument(
        "--mode",
        choices=["standard", "studio"],
        default="studio",
        help="Modo de ejecución: 'standard' (corte rápido BiRefNet) o 'studio' (pipeline multicapa con sombras y profundidad).",
    )
    parser.add_argument(
        "--bg",
        default="white",
        type=str,
        help="Fondo deseado: 'white', 'transparent', o código Hex (#FFFFFF, #0F172A).",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        type=str,
        help="Prompt de texto para detección de objetos específicos (ej: 'product, shoes, person').",
    )
    parser.add_argument(
        "--device",
        choices=["auto", "cuda", "cpu"],
        default="auto",
        help="Dispositivo de aceleración para inferencia de redes neuronales.",
    )
    parser.add_argument(
        "--shadow-intensity",
        default=0.65,
        type=float,
        help="Intensidad de la sombra de contacto (0.0 a 1.0).",
    )
    parser.add_argument(
        "--shadow-blur",
        default=12.0,
        type=float,
        help="Radio de desenfoque de la sombra de contacto.",
    )
    parser.add_argument(
        "--no-shadows",
        action="store_true",
        help="Desactivar la proyección de sombras de contacto en modo studio.",
    )
    parser.add_argument(
        "--auto-crop",
        action="store_true",
        help="Ajustar automáticamente el encuadre al sujeto sin márgenes excesivos.",
    )
    parser.add_argument(
        "--format",
        choices=["auto", "JPEG", "PNG", "WEBP"],
        default="auto",
        help="Formato de archivo de salida.",
    )
    return parser.parse_args()


def get_images_from_path(input_path: Path) -> List[Path]:
    if input_path.is_file():
        return [input_path]
    elif input_path.is_dir():
        imgs = []
        for p in input_path.iterdir():
            if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS:
                imgs.append(p)
        return sorted(imgs)
    return []


def determine_output_path(
    in_path: Path,
    out_target: Optional[Path],
    is_batch: bool,
    out_format: str,
    bg_color: str,
) -> Path:
    ext = ".png" if bg_color.lower() == "transparent" or out_format == "PNG" else ".jpg"
    if out_format == "WEBP":
        ext = ".webp"
    elif out_format == "JPEG":
        ext = ".jpg"

    if out_target is None:
        out_dir = Path("output")
        out_dir.mkdir(parents=True, exist_ok=True)
        return out_dir / f"{in_path.stem}_removed{ext}"

    if is_batch or out_target.is_dir() or not out_target.suffix:
        out_target.mkdir(parents=True, exist_ok=True)
        return out_target / f"{in_path.stem}_removed{ext}"

    out_target.parent.mkdir(parents=True, exist_ok=True)
    return out_target


def main():
    args = parse_args()
    input_path = Path(args.input)

    if not input_path.exists():
        logger.error(f"La ruta de entrada no existe: {input_path}")
        sys.exit(1)

    images = get_images_from_path(input_path)
    if not images:
        logger.warning(f"No se encontraron imágenes compatibles en: {input_path}")
        sys.exit(0)

    is_batch = len(images) > 1 or input_path.is_dir()
    out_target = Path(args.output) if args.output else None

    logger.info(f"=== Iniciando Background Remover ({args.mode.upper()} MODE) ===")
    logger.info(f"Total imágenes detectadas: {len(images)}")
    logger.info(f"Fondo: {args.bg} | Dispositivo: {args.device}")

    # Inicializar el pipeline correspondiente
    if args.mode == "studio":
        pipeline = StudioLayeredPipeline(device=args.device)
    else:
        pipeline = StandardPipeline(device=args.device)

    total_ok = 0
    total_err = 0

    for idx, img_path in enumerate(images, 1):
        logger.info(f"[{idx}/{len(images)}] Procesando: {img_path.name}")
        out_file = determine_output_path(img_path, out_target, is_batch, args.format, args.bg)

        try:
            if args.mode == "studio":
                res_img, meta = pipeline.process(
                    image_input=img_path,
                    text_prompt=args.prompt,
                    bg_color=args.bg,
                    apply_shadows=not args.no_shadows,
                    shadow_intensity=args.shadow_intensity,
                    shadow_blur=args.shadow_blur,
                    auto_crop=args.auto_crop,
                )
            else:
                res_img, meta = pipeline.process(
                    image_input=img_path,
                    bg_color=args.bg,
                    auto_crop=args.auto_crop,
                )

            # Guardar imagen resultante
            save_format = "PNG" if out_file.suffix.lower() == ".png" else "JPEG"
            if out_file.suffix.lower() == ".webp":
                save_format = "WEBP"

            if save_format == "JPEG" and res_img.mode != "RGB":
                res_img = res_img.convert("RGB")

            res_img.save(out_file, format=save_format, quality=95)
            logger.info(f"  -> Guardado exitosamente en: {out_file}")
            total_ok += 1

        except Exception as e:
            logger.error(f"  -> Fallo procesando {img_path.name}: {e}")
            total_err += 1

    logger.info(f"\nProceso finalizado. Exitosas: {total_ok} | Fallidas: {total_err}")


if __name__ == "__main__":
    main()
