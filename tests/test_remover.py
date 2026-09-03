"""Suite de pruebas unitarias para el sistema Background Remover."""

import unittest
from pathlib import Path
from PIL import Image, ImageDraw

from modules.models.config import config, ProcessingConfig
from modules.models.error_codes import ErrorCode, get_error_detail
from modules.utils.helpers import parse_color_string, format_bytes, CircuitBreaker
from modules.services.image_processor import ImageProcessor
from modules.services.file_manager import FileManager
from modules.services.tracker_service import ProcessingTracker
from modules.services.bg_remover_service import BackgroundRemoverService
from modules.services.batch_service import BatchProcessingService


class TestBackgroundRemover(unittest.TestCase):

    def setUp(self):
        self.test_dir = Path("tests_scratch")
        self.test_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        import shutil
        if self.test_dir.exists():
            shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_color_parser(self):
        self.assertEqual(parse_color_string("white"), (255, 255, 255, 255))
        self.assertEqual(parse_color_string("#FFFFFF"), (255, 255, 255, 255))
        self.assertEqual(parse_color_string("255,255,255"), (255, 255, 255, 255))
        self.assertEqual(parse_color_string("transparent"), (0, 0, 0, 0))
        self.assertEqual(parse_color_string("#00FF00"), (0, 255, 0, 255))

    def test_format_bytes(self):
        self.assertEqual(format_bytes(500), "500.0 B")
        self.assertEqual(format_bytes(1024 * 1024), "1.0 MB")

    def test_circuit_breaker(self):
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=0.1)
        self.assertTrue(cb.can_execute())
        cb.record_failure()
        self.assertTrue(cb.can_execute())
        cb.record_failure()
        self.assertFalse(cb.can_execute())

    def test_image_processor_solid_white_background(self):
        img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        draw.ellipse((25, 25, 75, 75), fill=(255, 0, 0, 255))

        processor = ImageProcessor()
        composed = processor.apply_solid_background(img, bg_color=(255, 255, 255, 255))

        self.assertEqual(composed.getpixel((0, 0)), (255, 255, 255))
        self.assertEqual(composed.getpixel((99, 99)), (255, 255, 255))
        self.assertEqual(composed.getpixel((50, 50)), (255, 0, 0))

    def test_error_codes(self):
        detail = get_error_detail(ErrorCode.CONFIG_INVALID_COLOR)
        self.assertIsNotNone(detail)
        self.assertEqual(detail.code, "ERR_1001")

    def test_file_manager_and_tracker(self):
        tracker_file = self.test_dir / "tracker.json"
        tracker = ProcessingTracker(tracker_file)
        tracker.record_job("test.jpg", "test_out.jpg", True, 1.5, "100x100", 1000, 800)
        
        summary = tracker.get_summary()
        self.assertEqual(summary["total_processed"], 1)
        self.assertEqual(summary["successful"], 1)

    def test_end_to_end_pipeline(self):
        test_img_path = self.test_dir / "sample_ball.png"
        img = Image.new("RGB", (200, 200), (0, 150, 255))
        draw = ImageDraw.Draw(img)
        draw.ellipse((50, 50, 150, 150), fill=(255, 200, 0))
        img.save(test_img_path)

        out_img_path = self.test_dir / "sample_ball_white_bg.jpg"

        batch_service = BatchProcessingService()
        success, out_path, err = batch_service.process_single_image(
            input_path=test_img_path,
            output_path=out_img_path,
            bg_color="white"
        )

        self.assertTrue(success, f"Pipeline falló con error: {err}")
        self.assertIsNotNone(out_path)
        self.assertTrue(out_path.exists())

        result_img = Image.open(out_path)
        self.assertEqual(result_img.mode, "RGB")
        corner_pixel = result_img.getpixel((5, 5))
        self.assertTrue(all(val > 240 for val in corner_pixel))

    def test_gui_initialization(self):
        from modules.ui.app_gui import BackgroundRemoverGUI
        # BackgroundRemoverGUI se inicializa de forma headless para pruebas sin ventana activa
        app = BackgroundRemoverGUI()
        self.assertIsNotNone(app)
        self.assertEqual(app.mode_var.get(), "file")
        self.assertGreater(app.batch_limit_var.get(), 0)
        app.destroy()

    def test_batch_limit_enforcement(self):
        # Crear 5 imágenes de prueba
        image_paths = []
        for i in range(5):
            p = self.test_dir / f"img_{i}.jpg"
            img = Image.new("RGB", (50, 50), (i * 40, 100, 100))
            img.save(p)
            image_paths.append(p)

        batch_service = BatchProcessingService()
        # Procesar con límite de 2
        results = batch_service.process_batch(
            images=image_paths,
            output_dir=self.test_dir / "out_limit",
            limit=2
        )
        self.assertEqual(results["total"], 2)

    def test_heic_extension_support(self):
        fm = FileManager()
        heic_file = self.test_dir / "sample.heic"
        heic_file.touch()
        heic_upper = self.test_dir / "sample2.HEIC"
        heic_upper.touch()
        heif_file = self.test_dir / "sample3.heif"
        heif_file.touch()
        txt_file = self.test_dir / "notes.txt"
        txt_file.touch()

        self.assertTrue(fm.is_supported_image(heic_file))
        self.assertTrue(fm.is_supported_image(heic_upper))
        self.assertTrue(fm.is_supported_image(heif_file))
        self.assertFalse(fm.is_supported_image(txt_file))

    def test_heic_output_format_mapping(self):
        fm = FileManager()
        heic_path = Path("C:/photos/vacation.HEIC")

        out_jpeg = fm.determine_output_path(heic_path, output_format="JPEG")
        self.assertEqual(out_jpeg.name, "vacation_white_bg.jpg")

        out_png = fm.determine_output_path(heic_path, output_format="PNG")
        self.assertEqual(out_png.name, "vacation_white_bg.png")

        out_webp = fm.determine_output_path(heic_path, output_format="WEBP")
        self.assertEqual(out_webp.name, "vacation_white_bg.webp")

    def test_heic_processing_and_conversion(self):
        # Crear una imagen sintética y guardarla en formato HEIC
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            self.skipTest("pillow-heif no instalado")

        heic_input = self.test_dir / "test_apple_photo.heic"
        img = Image.new("RGB", (120, 120), (50, 100, 200))
        draw = ImageDraw.Draw(img)
        draw.rectangle((30, 30, 90, 90), fill=(255, 100, 50))
        img.save(heic_input, format="HEIF")

        self.assertTrue(heic_input.exists())

        batch_service = BatchProcessingService()
        
        # 1. Proceso con salida JPEG
        success_jpg, out_jpg, err_jpg = batch_service.process_single_image(
            input_path=heic_input,
            output_format="JPEG",
            bg_color="white"
        )
        self.assertTrue(success_jpg, f"Fallo al procesar HEIC a JPEG: {err_jpg}")
        self.assertIsNotNone(out_jpg)
        self.assertEqual(out_jpg.suffix.lower(), ".jpg")
        self.assertTrue(out_jpg.exists())

        # 2. Proceso con salida PNG
        success_png, out_png, err_png = batch_service.process_single_image(
            input_path=heic_input,
            output_format="PNG",
            bg_color="transparent"
        )
        self.assertTrue(success_png, f"Fallo al procesar HEIC a PNG: {err_png}")
        self.assertIsNotNone(out_png)
        self.assertEqual(out_png.suffix.lower(), ".png")
        self.assertTrue(out_png.exists())


if __name__ == "__main__":
    unittest.main()

