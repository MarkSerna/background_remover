"""
Interfaz Gráfica moderna, estética y compacta construida con Flet para Background Remover Pro.
Diseño Zero-Scroll (vista única sin desplazamiento vertical):
  - Encabezado ultra-compacto con branding Altikore y badge PRO AI
  - Selector de modo y rutas con FilePicker nativo
  - Panel de ajustes compacto con swatch de color, selector modal y SegmentedButtons
  - Vista previa en vivo Antes vs. Después (Side-by-side) de altura optimizada
  - Copiado de 1 clic al portapapeles de Windows (formato DIB)
  - Barra de telemetría y consola de logs compacta
  - Barra de acción inferior con botón prominente de procesamiento
"""

import os
import sys
import io
import time
import base64
import threading
import logging
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps
import flet as ft

try:
    import win32clipboard
    HAS_CLIPBOARD = True
except Exception:
    HAS_CLIPBOARD = False

from modules.models.config import config
from modules.models.settings_manager import settings_manager
from modules.services.batch_service import BatchProcessingService
from modules.services.file_manager import FileManager
from modules.utils.helpers import parse_color_string

logger = logging.getLogger(__name__)

# Paleta de diseño Studio Dark
BG_APP = "#0A0E17"
CARD_BG = "#131B2E"
CARD_INNER = "#090D16"
BORDER_COLOR = "#22304A"
BORDER_SUBTLE = "#1A2538"
ACCENT = "#2563EB"
ACCENT_LIGHT = "#3B82F6"
SUCCESS = "#10B981"
WARNING = "#F59E0B"
DANGER = "#EF4444"
TEXT_PRIMARY = "#F8FAFC"
TEXT_MUTED = "#94A3B8"
TEXT_DIM = "#64748B"

ICON_ICO = Path("assets/app_icon.ico")


class _VarAdapter:
    """Adaptador de compatibilidad para acceso reactivo simple tipo .get() / .set()."""
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, val):
        self._value = val


class BackgroundRemoverGUI:
    """Controlador y vista principal con diseño compacto Zero-Scroll."""

    def __init__(self, page: Optional[ft.Page] = None):
        saved_output = settings_manager.get("output_dir", "")
        default_out = saved_output if saved_output and Path(saved_output).exists() else str(config.output_dir.resolve())

        self.mode = "file"
        self.input_path = ""
        self.output_dir = default_out
        self.bg_color = settings_manager.get("bg_color", "white")
        self.bg_color_hex = settings_manager.get("bg_color_hex", "#FFFFFF")
        self.output_format = settings_manager.get("output_format", "JPEG")
        self.auto_crop = bool(settings_manager.get("auto_crop", False))
        self.alpha_matting = bool(settings_manager.get("alpha_matting", False))
        self.batch_limit = int(settings_manager.get("batch_limit", config.processing.batch_limit) or 20)
        self.model_name = settings_manager.get("model_name", "auto")
        self.is_processing = False

        # Adaptadores para pruebas unitarias y retrocompatibilidad
        self.mode_var = _VarAdapter(self.mode)
        self.input_path_var = _VarAdapter(self.input_path)
        self.output_dir_var = _VarAdapter(self.output_dir)
        self.bg_color_var = _VarAdapter(self.bg_color)
        self.format_var = _VarAdapter(self.output_format)
        self.auto_crop_var = _VarAdapter(self.auto_crop)
        self.alpha_matting_var = _VarAdapter(self.alpha_matting)
        self.batch_limit_var = _VarAdapter(self.batch_limit)
        self.model_mode_var = _VarAdapter(self.model_name)

        # Estado en memoria
        self.current_orig_pil: Optional[Image.Image] = None
        self.current_res_pil: Optional[Image.Image] = None

        # Servicios
        self.file_manager = FileManager(config)
        self.batch_service = BatchProcessingService(config, file_manager=self.file_manager)

        self.page: Optional[ft.Page] = page
        if self.page is not None:
            self._setup_page()

    def destroy(self):
        """Finalización limpia de ventana."""
        if self.page:
            try:
                self.page.window.close()
            except Exception:
                pass

    def _setup_page(self):
        """Configuración de ventana ajustada para Zero-Scroll absoluto."""
        page = self.page
        page.title = "Background Remover Pro — Fondo Blanco Inteligente"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = BG_APP
        page.padding = 10
        page.scroll = None  # Cero scroll garantizado

        # Dimensiones optimizadas para pantallas estándar (768p / 800p / 900p / 1080p)
        page.window.width = 960
        page.window.height = 800
        page.window.min_width = 900
        page.window.min_height = 700
        page.window.resizable = True
        page.run_task(page.window.center)

        if ICON_ICO.exists():
            page.window.icon = str(ICON_ICO.resolve())

        self._build_ui()

    def _build_ui(self):
        page = self.page

        # Servicio nativo de selección de archivos
        self.file_picker = ft.FilePicker()
        if self.file_picker not in page.services:
            page.services.append(self.file_picker)

        # ==============================================================================
        # 1. HEADER COMPACTO CON BRANDING (altura ~36px)
        # ==============================================================================
        header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("✨", size=18),
                            ft.Text("Background Remover", size=15, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            ft.Container(
                                content=ft.Text("PRO AI", size=8, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                bgcolor=ACCENT,
                                padding=ft.Padding.symmetric(horizontal=5, vertical=1),
                                border_radius=4,
                            ),
                            ft.Text("•  Fondo Blanco Inteligente & Aislamiento con IA", size=11, color=TEXT_MUTED),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.VERIFIED_ROUNDED, size=13, color=ACCENT_LIGHT),
                                ft.Text("Desarrollado por Altikore", size=10, weight=ft.FontWeight.BOLD, color=ACCENT_LIGHT),
                            ],
                            spacing=4,
                        ),
                        bgcolor=CARD_INNER,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                        border_radius=12,
                        border=ft.Border.all(1, BORDER_COLOR),
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            bgcolor=CARD_BG,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=12, vertical=6),
            border=ft.Border.all(1, BORDER_COLOR),
        )

        # ==============================================================================
        # 2. SECCIÓN: MODO Y RUTAS DE ARCHIVOS (altura ~86px)
        # ==============================================================================
        self.seg_mode = ft.SegmentedButton(
            [
                ft.Segment(value="file", label=ft.Text("Archivo individual", size=11), icon=ft.Icon(ft.Icons.IMAGE_OUTLINED, size=14)),
                ft.Segment(value="folder", label=ft.Text("Carpeta en Lote", size=11), icon=ft.Icon(ft.Icons.FOLDER_SPECIAL_OUTLINED, size=14)),
            ],
            selected=["file"],
            allow_multiple_selection=False,
            on_change=self._on_segmented_mode_change,
        )

        self.txt_input_path = ft.TextField(
            value=self.input_path,
            hint_text="Seleccione o examine una imagen compatible (JPG, PNG, WEBP, HEIC, etc.)...",
            prefix_icon=ft.Icons.INSERT_DRIVE_FILE_OUTLINED,
            text_size=11,
            dense=True,
            expand=True,
            bgcolor=CARD_INNER,
            border_color=BORDER_COLOR,
            border_radius=6,
            on_change=self._on_input_text_change,
        )

        self.txt_output_path = ft.TextField(
            value=self.output_dir,
            hint_text="Carpeta de destino para las imágenes procesadas...",
            prefix_icon=ft.Icons.FOLDER_OUTLINED,
            text_size=11,
            dense=True,
            expand=True,
            bgcolor=CARD_INNER,
            border_color=BORDER_COLOR,
            border_radius=6,
            on_change=self._on_output_text_change,
        )

        input_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.FOLDER_OPEN_ROUNDED, size=14, color=ACCENT_LIGHT),
                                    ft.Text("1. Modo y Ubicación:", size=11, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                ],
                                spacing=6,
                            ),
                            self.seg_mode,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text("Origen:", size=11, color=TEXT_MUTED, width=52),
                            self.txt_input_path,
                            ft.ElevatedButton(
                                "Examinar",
                                icon=ft.Icons.FOLDER_OPEN,
                                bgcolor=ACCENT,
                                color=TEXT_PRIMARY,
                                height=30,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                                on_click=self._browse_input,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text("Destino:", size=11, color=TEXT_MUTED, width=52),
                            self.txt_output_path,
                            ft.ElevatedButton(
                                "Examinar",
                                icon=ft.Icons.DRIVE_FOLDER_UPLOAD,
                                bgcolor="#1E293B",
                                color=TEXT_PRIMARY,
                                height=30,
                                style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=6)),
                                on_click=self._browse_output,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=6,
                    ),
                ],
                spacing=5,
            ),
            bgcolor=CARD_BG,
            border_radius=8,
            padding=ft.Padding.all(8),
            border=ft.Border.all(1, BORDER_COLOR),
        )

        # ==============================================================================
        # 3. SECCIÓN: AJUSTES Y MOTOR DE IA (altura ~92px)
        # ==============================================================================
        self.color_swatch = ft.Container(
            width=16,
            height=16,
            bgcolor=self.bg_color_hex,
            border_radius=4,
            border=ft.Border.all(1, "#FFFFFF" if self.bg_color == "white" else BORDER_COLOR),
        )

        self.seg_format = ft.SegmentedButton(
            [
                ft.Segment(value="JPEG", label=ft.Text("JPEG", size=10)),
                ft.Segment(value="PNG", label=ft.Text("PNG", size=10)),
                ft.Segment(value="WEBP", label=ft.Text("WEBP", size=10)),
            ],
            selected=[self.output_format],
            allow_multiple_selection=False,
            on_change=self._on_segmented_format_change,
        )

        self.dropdown_model = ft.Dropdown(
            options=[
                ft.dropdown.Option("auto", "auto (Detección Automática Inteligente)"),
                ft.dropdown.Option("bria-rmbg", "bria-rmbg (SOTA Preciso - Fotografía y Productos)"),
                ft.dropdown.Option("birefnet-general", "birefnet-general (Alta Definición)"),
                ft.dropdown.Option("u2net_human_seg", "u2net_human_seg (Retratos y Personas)"),
                ft.dropdown.Option("u2net", "u2net (Modelo General)"),
                ft.dropdown.Option("isnet-general-use", "isnet-general-use (Objetos)"),
                ft.dropdown.Option("silueta", "silueta (Ultra Rápido - Bajo Consumo)"),
            ],
            value=self.model_name,
            text_size=10,
            dense=True,
            width=280,
            bgcolor=CARD_INNER,
            border_color=BORDER_COLOR,
            border_radius=6,
            on_select=self._on_model_change,
        )

        self.txt_batch_limit = ft.TextField(
            value=str(self.batch_limit),
            width=50,
            text_size=10,
            text_align=ft.TextAlign.CENTER,
            dense=True,
            bgcolor=CARD_INNER,
            border_color=BORDER_COLOR,
            border_radius=6,
            on_change=self._on_batch_limit_change,
        )

        self.switch_auto_crop = ft.Switch(
            label="Auto-crop",
            value=self.auto_crop,
            active_color=ACCENT_LIGHT,
            on_change=lambda e: setattr(self, "auto_crop", e.control.value),
        )

        self.switch_alpha_matting = ft.Switch(
            label="Alpha Matting",
            value=self.alpha_matting,
            active_color=ACCENT_LIGHT,
            on_change=lambda e: setattr(self, "alpha_matting", e.control.value),
        )

        settings_card = ft.Container(
            content=ft.Column(
                controls=[
                    # Fila 1: Color de Fondo y Formato
                    ft.Row(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Row(
                                        controls=[
                                            ft.Icon(ft.Icons.PALETTE_OUTLINED, size=14, color=ACCENT_LIGHT),
                                            ft.Text("2. Ajustes:", size=11, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                        ],
                                        spacing=5,
                                    ),
                                    ft.Text("Fondo:", size=10, color=TEXT_MUTED),
                                    self.color_swatch,
                                    ft.OutlinedButton(
                                        "Blanco",
                                        height=26,
                                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5)),
                                        on_click=lambda _: self._set_preset_color("white", "#FFFFFF"),
                                    ),
                                    ft.OutlinedButton(
                                        "PNG Transp.",
                                        height=26,
                                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5)),
                                        on_click=lambda _: self._set_preset_color("transparent", "#1E293B"),
                                    ),
                                    ft.OutlinedButton(
                                        "Personalizado...",
                                        height=26,
                                        style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5)),
                                        on_click=self._open_custom_color_dialog,
                                    ),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=6,
                            ),
                            ft.Row(
                                controls=[
                                    ft.Text("Formato:", size=10, color=TEXT_MUTED),
                                    self.seg_format,
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=6,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    # Fila 2: Modelo IA + Límite + Switches
                    ft.Row(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text("Modelo IA:", size=10, color=TEXT_MUTED),
                                    self.dropdown_model,
                                ],
                                spacing=5,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            ft.Row(
                                controls=[
                                    ft.Text("Límite:", size=10, color=TEXT_MUTED),
                                    self.txt_batch_limit,
                                ],
                                spacing=5,
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                            ),
                            self.switch_auto_crop,
                            self.switch_alpha_matting,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=10,
                    ),
                    # Fila 3: Advertencia recomendada
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.LIGHTBULB_OUTLINE_ROUNDED, color=WARNING, size=13),
                                ft.Text(
                                    "Recomendado: 20 imágenes por intento para máxima estabilidad. Amplíe según la memoria de su equipo.",
                                    size=9.5,
                                    weight=ft.FontWeight.W_500,
                                    color=WARNING,
                                ),
                            ],
                            spacing=6,
                        ),
                        bgcolor="#291A04",
                        border_radius=5,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=3),
                        border=ft.Border.all(1, "#523608"),
                    ),
                ],
                spacing=5,
            ),
            bgcolor=CARD_BG,
            border_radius=8,
            padding=ft.Padding.all(8),
            border=ft.Border.all(1, BORDER_COLOR),
        )

        # ==============================================================================
        # 4. SECCIÓN: PREVISUALIZACIÓN EN VIVO LADO A LADO (altura ~220px)
        # ==============================================================================
        self.img_orig_placeholder = ft.Column(
            controls=[
                ft.Icon(ft.Icons.ADD_PHOTO_ALTERNATE_OUTLINED, size=40, color=TEXT_DIM),
                ft.Text("Seleccione una imagen o presione Examinar", size=11, color=TEXT_MUTED, weight=ft.FontWeight.W_500),
                ft.Text("JPG, PNG, WEBP, BMP, TIFF, HEIC", size=9, color=TEXT_DIM),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        )

        self.img_orig_view = ft.Image(
            src="",
            fit=ft.BoxFit.CONTAIN,
            visible=False,
            border_radius=6,
        )

        self.img_res_placeholder = ft.Column(
            controls=[
                ft.Icon(ft.Icons.AUTO_AWESOME_OUTLINED, size=40, color=TEXT_DIM),
                ft.Text("El resultado procesado aparecerá aquí", size=11, color=TEXT_MUTED, weight=ft.FontWeight.W_500),
                ft.Text("Listo para guardar o copiar al portapapeles", size=9, color=TEXT_DIM),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=2,
        )

        self.img_res_view = ft.Image(
            src="",
            fit=ft.BoxFit.CONTAIN,
            visible=False,
            border_radius=6,
        )

        self.btn_copy_clipboard = ft.ElevatedButton(
            "📋 Copiar al Portapapeles",
            height=28,
            disabled=True,
            bgcolor="#1E3A5F",
            color=TEXT_PRIMARY,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=5)),
            on_click=self._copy_result_to_clipboard,
        )

        preview_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Icon(ft.Icons.REMOVE_RED_EYE_OUTLINED, size=14, color=ACCENT_LIGHT),
                                    ft.Text("3. Previsualización en Vivo — Antes vs. Después", size=11, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                ],
                                spacing=6,
                            ),
                            self.btn_copy_clipboard,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(
                        controls=[
                            # Cuadro Imagen Original
                            ft.Container(
                                content=ft.Column(
                                    controls=[
                                        ft.Container(
                                            content=ft.Row(
                                                controls=[
                                                    ft.Icon(ft.Icons.IMAGE_OUTLINED, size=12, color=TEXT_MUTED),
                                                    ft.Text("IMAGEN ORIGINAL", size=9, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
                                                ],
                                                spacing=4,
                                            ),
                                            bgcolor="#0C1322",
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                            border_radius=4,
                                        ),
                                        ft.Container(
                                            content=ft.Stack(
                                                controls=[
                                                    self.img_orig_placeholder,
                                                    self.img_orig_view,
                                                ],
                                                alignment=ft.Alignment.CENTER,
                                            ),
                                            expand=True,
                                            alignment=ft.Alignment.CENTER,
                                        ),
                                    ],
                                    spacing=4,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                bgcolor=CARD_INNER,
                                border_radius=8,
                                padding=6,
                                expand=True,
                                height=220,
                                border=ft.Border.all(1, BORDER_COLOR),
                            ),
                            # Cuadro Imagen Resultado
                            ft.Container(
                                content=ft.Column(
                                    controls=[
                                        ft.Container(
                                            content=ft.Row(
                                                controls=[
                                                    ft.Icon(ft.Icons.AUTO_AWESOME, size=12, color=SUCCESS),
                                                    ft.Text("FONDO BLANCO / RESULTADO", size=9, weight=ft.FontWeight.BOLD, color=SUCCESS),
                                                ],
                                                spacing=4,
                                            ),
                                            bgcolor="#061F14",
                                            padding=ft.Padding.symmetric(horizontal=8, vertical=2),
                                            border_radius=4,
                                        ),
                                        ft.Container(
                                            content=ft.Stack(
                                                controls=[
                                                    self.img_res_placeholder,
                                                    self.img_res_view,
                                                ],
                                                alignment=ft.Alignment.CENTER,
                                            ),
                                            expand=True,
                                            alignment=ft.Alignment.CENTER,
                                        ),
                                    ],
                                    spacing=4,
                                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                                ),
                                bgcolor=CARD_INNER,
                                border_radius=8,
                                padding=6,
                                expand=True,
                                height=220,
                                border=ft.Border.all(1, BORDER_COLOR),
                            ),
                        ],
                        spacing=8,
                    ),
                ],
                spacing=6,
            ),
            bgcolor=CARD_BG,
            border_radius=8,
            padding=ft.Padding.all(8),
            border=ft.Border.all(1, BORDER_COLOR),
        )

        # ==============================================================================
        # 5. SECCIÓN: ESTADO DEL MOTOR IA Y REGISTRO DE CONSOLA (altura ~82px)
        # ==============================================================================
        self.lbl_model_status = ft.Text(
            "⚡ Selección automática activa: analiza cada imagen y aplica el modelo óptimo (SOTA RMBG).",
            size=10,
            color=TEXT_MUTED,
        )

        self.progress_bar = ft.ProgressBar(
            value=0.0,
            color=ACCENT_LIGHT,
            bgcolor="#1E293B",
            height=4,
            border_radius=2,
        )

        self.txt_log = ft.TextField(
            multiline=True,
            read_only=True,
            min_lines=2,
            max_lines=2,
            text_size=9.5,
            text_style=ft.TextStyle(font_family="Consolas"),
            bgcolor=CARD_INNER,
            border_color=BORDER_COLOR,
            border_radius=6,
            expand=True,
        )

        status_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=self.lbl_model_status,
                        bgcolor=CARD_INNER,
                        border_radius=6,
                        padding=ft.Padding.symmetric(horizontal=8, vertical=4),
                        border=ft.Border.all(1, BORDER_COLOR),
                    ),
                    self.progress_bar,
                    self.txt_log,
                ],
                spacing=4,
            ),
            bgcolor=CARD_BG,
            border_radius=8,
            padding=ft.Padding.all(8),
            border=ft.Border.all(1, BORDER_COLOR),
        )

        # ==============================================================================
        # 6. BARRA DE ACCIÓN INFERIOR (altura ~36px)
        # ==============================================================================
        self.btn_open_folder = ft.ElevatedButton(
            "📁 Abrir Carpeta Destino",
            height=36,
            bgcolor="#1E293B",
            color=TEXT_PRIMARY,
            style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8)),
            on_click=self._open_output_folder,
        )

        self.btn_process = ft.ElevatedButton(
            "🚀 PROCESAR Y CAMBIAR A BLANCO",
            height=36,
            bgcolor=ACCENT,
            color=TEXT_PRIMARY,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=ft.Padding.symmetric(horizontal=24),
            ),
            on_click=self._start_processing_thread,
        )

        actions_row = ft.Row(
            controls=[
                self.btn_open_folder,
                self.btn_process,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        )

        # Inserción en la página con espaciado ultra-compacto
        page.add(
            ft.Column(
                controls=[
                    header,
                    input_card,
                    settings_card,
                    preview_card,
                    status_card,
                    actions_row,
                ],
                spacing=6,
            )
        )

        self._log("Listo. Seleccione una imagen o carpeta y presione Procesar.")
        page.update()

    # ------------------------------------------------------------------
    # Previsualización e imágenes
    # ------------------------------------------------------------------
    def _pil_to_base64(self, pil_img: Image.Image, max_size=(500, 300)) -> str:
        """Convierte una imagen PIL a base64 escalándola de forma nítida."""
        img = pil_img.copy()
        img.thumbnail(max_size, Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{encoded}"

    def _load_original_preview(self, img_path: Path):
        """Carga y muestra el thumbnail de la imagen original."""
        try:
            pil_img = Image.open(img_path)
            pil_img = ImageOps.exif_transpose(pil_img)
            self.current_orig_pil = pil_img
            data_uri = self._pil_to_base64(pil_img)

            if self.page:
                self.img_orig_placeholder.visible = False
                self.img_orig_view.src = data_uri
                self.img_orig_view.visible = True
                self.page.update()
        except Exception as e:
            logger.debug(f"Error cargando thumbnail original: {e}")

    def _update_result_preview(self, result_path: Path):
        """Carga y muestra el thumbnail del resultado procesado."""
        try:
            pil_img = Image.open(result_path)
            self.current_res_pil = pil_img
            data_uri = self._pil_to_base64(pil_img)

            if self.page:
                self.img_res_placeholder.visible = False
                self.img_res_view.src = data_uri
                self.img_res_view.visible = True
                if HAS_CLIPBOARD:
                    self.btn_copy_clipboard.disabled = False
                    self.btn_copy_clipboard.bgcolor = SUCCESS
                self.page.update()
        except Exception as e:
            logger.debug(f"Error cargando thumbnail resultado: {e}")

    # ------------------------------------------------------------------
    # Manejadores de eventos
    # ------------------------------------------------------------------
    def _on_segmented_mode_change(self, e):
        selected_val = e.control.selected
        if selected_val:
            self.mode = list(selected_val)[0] if isinstance(selected_val, (list, set)) else str(selected_val)
            self.mode_var.set(self.mode)
            if self.mode == "file":
                self.txt_input_path.hint_text = "Seleccione una imagen compatible (JPG, PNG, WEBP, HEIC, etc.)..."
            else:
                self.txt_input_path.hint_text = "Seleccione una carpeta con imágenes..."
            if self.page:
                self.page.update()

    def _on_segmented_format_change(self, e):
        selected_val = e.control.selected
        if selected_val:
            self.output_format = list(selected_val)[0] if isinstance(selected_val, (list, set)) else str(selected_val)
            self.format_var.set(self.output_format)

    def _on_input_text_change(self, e):
        self.input_path = e.control.value.strip()
        self.input_path_var.set(self.input_path)
        p = Path(self.input_path)
        if p.exists() and p.is_file():
            self._load_original_preview(p)

    def _on_output_text_change(self, e):
        self.output_dir = e.control.value.strip()
        self.output_dir_var.set(self.output_dir)

    def _on_model_change(self, e):
        self.model_name = e.control.value
        self.model_mode_var.set(self.model_name)

    def _on_batch_limit_change(self, e):
        val = e.control.value.strip()
        try:
            self.batch_limit = int(val) if int(val) > 0 else 20
        except Exception:
            self.batch_limit = 20
        self.batch_limit_var.set(self.batch_limit)

    async def _browse_input(self, e):
        if self.mode == "file":
            files = await self.file_picker.pick_files(
                dialog_title="Seleccionar imagen",
                allowed_extensions=["jpg", "jpeg", "png", "webp", "bmp", "tiff", "heic", "heif", "HEIC", "HEIF"],
                file_type=ft.FilePickerFileType.CUSTOM,
            )
            if files and len(files) > 0:
                p = Path(files[0].path)
                self.input_path = str(p.resolve())
                self.input_path_var.set(self.input_path)
                self.txt_input_path.value = self.input_path
                self._load_original_preview(p)
                self._log(f"📥 Archivo seleccionado: {p.name}")
                if self.page:
                    self.page.update()
        else:
            dir_path = await self.file_picker.get_directory_path(
                dialog_title="Seleccionar carpeta con imágenes",
            )
            if dir_path:
                p = Path(dir_path)
                self.input_path = str(p.resolve())
                self.input_path_var.set(self.input_path)
                self.txt_input_path.value = self.input_path
                self._log(f"📁 Carpeta seleccionada: {p.name}")
                if self.page:
                    self.page.update()

    async def _browse_output(self, e):
        dir_path = await self.file_picker.get_directory_path(
            dialog_title="Seleccionar carpeta de salida",
        )
        if dir_path:
            p = Path(dir_path)
            self.output_dir = str(p.resolve())
            self.output_dir_var.set(self.output_dir)
            self.txt_output_path.value = self.output_dir
            if self.page:
                self.page.update()

    def _set_preset_color(self, name: str, hex_val: str):
        self.bg_color = name
        self.bg_color_var.set(name)
        self.bg_color_hex = hex_val
        self.color_swatch.bgcolor = hex_val
        if name == "transparent":
            self.output_format = "PNG"
            self.format_var.set("PNG")
            self.seg_format.selected = ["PNG"]
        if self.page:
            self.page.update()

    def _open_custom_color_dialog(self, e):
        """Abre un diálogo interactivo para escoger color personalizado por paleta o Hex."""
        txt_custom_hex = ft.TextField(
            value=self.bg_color_hex,
            label="Código Hex (#RRGGBB)",
            dense=True,
            width=180,
            text_size=12,
            border_radius=8,
        )

        color_presets = [
            ("#FFFFFF", "Blanco Estudio"),
            ("#F1F5F9", "Gris Claro"),
            ("#94A3B8", "Gris Medio"),
            ("#0F172A", "Negro Profundo"),
            ("#EF4444", "Rojo Carmín"),
            ("#3B82F6", "Azul Eléctrico"),
            ("#10B981", "Verde Esmeralda"),
            ("#F59E0B", "Ámbar Dorado"),
        ]

        def pick_preset(hex_code):
            txt_custom_hex.value = hex_code
            if self.page:
                self.page.update()

        preset_chips = [
            ft.Container(
                content=ft.Row(
                    controls=[
                        ft.Container(width=12, height=12, bgcolor=hex_code, border_radius=3),
                        ft.Text(label, size=11, color=TEXT_PRIMARY),
                    ],
                    spacing=6,
                ),
                bgcolor=CARD_INNER,
                border=ft.Border.all(1, BORDER_COLOR),
                border_radius=6,
                padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                on_click=lambda _, h=hex_code: pick_preset(h),
            )
            for hex_code, label in color_presets
        ]

        def apply_color(_):
            val = txt_custom_hex.value.strip()
            if not val.startswith("#"):
                val = f"#{val}"
            try:
                parse_color_string(val)
                self.bg_color = val
                self.bg_color_var.set(val)
                self.bg_color_hex = val
                self.color_swatch.bgcolor = val
                self.page.pop_dialog()
                self.page.update()
            except Exception:
                self._show_alert("Color Inválido", "El formato ingresado no es un color hexadecimal válido (ej: #FFFFFF).")

        dlg = ft.AlertDialog(
            title=ft.Text("Color de Fondo Personalizado", size=15, weight=ft.FontWeight.BOLD),
            content=ft.Column(
                controls=[
                    ft.Text("Seleccione un color predefinido o escriba el código hexadecimal:", size=11, color=TEXT_MUTED),
                    ft.Row(controls=preset_chips, wrap=True, spacing=8),
                    txt_custom_hex,
                ],
                spacing=12,
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.ElevatedButton("Aplicar Color", bgcolor=ACCENT, color=TEXT_PRIMARY, on_click=apply_color),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def _copy_result_to_clipboard(self, e):
        """Copia la imagen procesada resultante al portapapeles de Windows en formato DIB."""
        if not HAS_CLIPBOARD or self.current_res_pil is None:
            self._show_alert("Atención", "No hay imagen procesada disponible para copiar.")
            return
        try:
            out = io.BytesIO()
            self.current_res_pil.convert("RGB").save(out, "BMP")
            data = out.getvalue()[14:]  # Omitir encabezado BMP de 14 bytes
            out.close()

            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()

            self._show_snackbar("¡Imagen copiada al portapapeles! Puedes pegarla con Ctrl+V.")
            self._log("📋 Imagen copiada al portapapeles de Windows (Ctrl+V listo).")
        except Exception as err:
            self._show_alert("Error", f"No se pudo copiar al portapapeles: {err}")

    def _open_output_folder(self, e):
        out = Path(self.output_dir or "output")
        out.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(out.resolve()))
        except Exception as err:
            self._show_alert("Error", f"No se pudo abrir la carpeta de destino: {err}")

    def _log(self, msg: str):
        logger.info(msg)
        if self.page:
            current = self.txt_log.value or ""
            self.txt_log.value = f"{current}\n{msg}".strip() if current else msg
            self.page.update()

    def _show_alert(self, title: str, message: str):
        if not self.page:
            return
        dlg = ft.AlertDialog(
            title=ft.Text(title, weight=ft.FontWeight.BOLD),
            content=ft.Text(message),
            actions=[
                ft.TextButton("Aceptar", on_click=lambda _: self.page.pop_dialog())
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.show_dialog(dlg)

    def _show_snackbar(self, message: str):
        if not self.page:
            return
        self.page.show_dialog(ft.SnackBar(content=ft.Text(message)))

    def _set_ui_state(self, processing: bool):
        self.is_processing = processing
        if self.page:
            self.btn_process.disabled = processing
            self.page.update()

    def _update_model_info(self, result):
        if not self.page:
            return
        if result is None:
            self.lbl_model_status.value = "  Modelo manual seleccionado."
            self.lbl_model_status.color = TEXT_MUTED
        else:
            pct = f"{result.confidence:.0%}"
            self.lbl_model_status.value = f"  🎯 Modelo aplicado: {result.model_name} ({pct} confianza) — {result.reason}"
            self.lbl_model_status.color = SUCCESS
        self.page.update()

    # ------------------------------------------------------------------
    # Procesamiento en segundo plano
    # ------------------------------------------------------------------
    def _start_processing_thread(self, e):
        if self.is_processing:
            return

        input_str = self.input_path.strip()
        output_str = self.output_dir.strip()

        if not input_str:
            self._show_alert("Atención", "Por favor seleccione una imagen o carpeta de origen.")
            return
        if not output_str:
            self._show_alert("Atención", "Por favor seleccione una carpeta de destino.")
            return

        input_path = Path(input_str)
        if not input_path.exists():
            self._show_alert("Error", f"La ruta de entrada no existe:\n{input_path}")
            return

        self.batch_service.config.processing.model_name = self.model_name
        self._save_user_preferences()

        self._set_ui_state(True)
        self.progress_bar.value = 0.0
        self.lbl_model_status.value = "  ⏳ Analizando imagen y ejecutando IA..."
        self.lbl_model_status.color = TEXT_MUTED
        if self.page:
            self.page.update()

        t = threading.Thread(target=self._run_processing, args=(input_path, Path(output_str)), daemon=True)
        t.start()

    def _run_processing(self, input_path: Path, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        bg_color = self.bg_color
        out_format = self.output_format
        auto_crop = self.auto_crop
        alpha_matting = self.alpha_matting
        self.batch_service.config.processing.alpha_matting = alpha_matting
        self.batch_service.config.processing.output_format = out_format

        if input_path.is_file():
            self._load_original_preview(input_path)
            self._log(f"\n--- Procesando: {input_path.name} ---")
            self.progress_bar.value = 0.3
            if self.page:
                self.page.update()

            success, out_path, err = self.batch_service.process_single_image(
                input_path=input_path,
                output_path=self.file_manager.determine_output_path(input_path, output_dir=output_dir, output_format=out_format),
                bg_color=bg_color,
                output_format=out_format,
                auto_crop=auto_crop,
            )
            self.progress_bar.value = 1.0
            sel = self.batch_service.remover.last_selection
            self._update_model_info(sel)

            if success:
                self._update_result_preview(out_path)
                self._log(f"[OK] Guardado: {out_path.name}")
                self._show_alert("Completado", f"¡Imagen procesada con éxito!\nGuardada en: {out_path}")
            else:
                self._log(f"[ERROR] {err}")
                self._show_alert("Error", f"No se pudo procesar:\n{err}")

        elif input_path.is_dir():
            images = self.file_manager.get_input_images(input_path)
            total_found = len(images)

            if total_found == 0:
                self._log("[AVISO] No se encontraron imágenes compatibles.")
                self._show_alert("Sin Imágenes", "No se encontraron imágenes compatibles.")
                self._set_ui_state(False)
                return

            limit = self.batch_limit if self.batch_limit > 0 else 20
            if total_found > limit:
                self._log(f"[AVISO] {total_found} imágenes detectadas. Procesando primeras {limit} según el límite configurado.")
                images = images[:limit]

            total = len(images)
            self._log(f"\n--- Lote: {total} imágenes (límite: {limit}) ---")
            ok = fail = 0

            for idx, img in enumerate(images, 1):
                self._log(f"[{idx}/{total}] {img.name}...")
                self._load_original_preview(img)
                dest = self.file_manager.determine_output_path(img, output_dir=output_dir, output_format=out_format)
                success, out_path, err = self.batch_service.process_single_image(
                    input_path=img,
                    output_path=dest,
                    bg_color=bg_color,
                    output_format=out_format,
                    auto_crop=auto_crop,
                )
                if success:
                    ok += 1
                    sel = self.batch_service.remover.last_selection
                    self._update_model_info(sel)
                    self._update_result_preview(out_path)
                    self._log(f"   -> [OK] {out_path.name}")
                else:
                    fail += 1
                    self._log(f"   -> [FALLO] {err}")

                self.progress_bar.value = idx / total
                if self.page:
                    self.page.update()

            self._log(f"\n[FINALIZADO] Exitosas: {ok}/{total} | Fallidas: {fail}/{total}")
            self._show_alert(
                "Lote Finalizado",
                f"Proceso por lotes finalizado:\n• Exitosas: {ok}\n• Fallidas: {fail}\n\nGuardadas en: {output_dir}",
            )

        self._set_ui_state(False)

    def _save_user_preferences(self):
        """Guarda las preferencias actuales en AppData."""
        try:
            settings_manager.save_settings({
                "output_dir": self.output_dir.strip(),
                "bg_color": self.bg_color,
                "bg_color_hex": self.bg_color_hex,
                "output_format": self.output_format,
                "auto_crop": self.auto_crop,
                "alpha_matting": self.alpha_matting,
                "batch_limit": self.batch_limit,
                "model_name": self.model_name,
            })
        except Exception as e:
            logger.debug(f"No se pudieron guardar preferencias: {e}")


def launch_gui(page: Optional[ft.Page] = None) -> None:
    """Punto de entrada de la interfaz gráfica con Flet."""
    if page is not None:
        BackgroundRemoverGUI(page)
    else:
        ft.run(lambda p: BackgroundRemoverGUI(p))


if __name__ == "__main__":
    launch_gui()
