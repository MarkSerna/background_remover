"""
Interfaz Gráfica moderna y de alto rendimiento construida con Flet para Background Remover.
Incluye:
  - Procesamiento individual y por lotes con selección de modelos de IA
  - Selección de archivos y carpetas mediante FilePicker nativo
  - Vista previa en vivo Antes vs. Después (Side-by-side)
  - Copiado de imagen procesada al portapapeles de Windows (1 clic, formato DIB)
  - Paleta interactiva para selección de color de fondo personalizado
  - Persistencia de preferencias en AppData
  - Consola de logs y barra de progreso en tiempo real
  - Diseño responsivo, elegante y moderno construido nativamente con Flet
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

# Paleta de colores visual
BG_DARK = "#0F172A"
SURFACE = "#1E293B"
SURFACE_INNER = "#0B132B"
BORDER = "#334155"
ACCENT = "#3B82F6"
ACCENT_HOVER = "#2563EB"
SUCCESS = "#22C55E"
WARNING = "#F59E0B"
DANGER = "#EF4444"
TEXT_PRIMARY = "#F8FAFC"
TEXT_MUTED = "#94A3B8"

ICON_ICO = Path("assets/app_icon.ico")
ICON_PNG = Path("assets/app_icon.png")


class _VarAdapter:
    """Adaptador de compatibilidad para acceso reactivo simple tipo .get() / .set()."""
    def __init__(self, value):
        self._value = value

    def get(self):
        return self._value

    def set(self, val):
        self._value = val


class BackgroundRemoverGUI:
    """Controlador y vista principal de la aplicación Background Remover con Flet."""

    def __init__(self, page: Optional[ft.Page] = None):
        # Cargar preferencias guardadas
        saved_output = settings_manager.get("output_dir", "")
        default_out = saved_output if saved_output and Path(saved_output).exists() else str(config.output_dir.resolve())

        self.mode = "file"
        self.input_path = ""
        self.output_dir = default_out
        self.bg_color = settings_manager.get("bg_color", "white")
        self.bg_color_hex = settings_manager.get("bg_color_hex", "#FFFFFF")
        self.output_format = settings_manager.get("output_format", "JPEG")
        self.auto_crop = settings_manager.get("auto_crop", False)
        self.alpha_matting = settings_manager.get("alpha_matting", False)
        self.batch_limit = int(settings_manager.get("batch_limit", config.processing.batch_limit) or 20)
        self.model_name = settings_manager.get("model_name", "auto")
        self.is_processing = False

        # Adaptadores para compatibilidad
        self.mode_var = _VarAdapter(self.mode)
        self.input_path_var = _VarAdapter(self.input_path)
        self.output_dir_var = _VarAdapter(self.output_dir)
        self.bg_color_var = _VarAdapter(self.bg_color)
        self.format_var = _VarAdapter(self.output_format)
        self.auto_crop_var = _VarAdapter(self.auto_crop)
        self.alpha_matting_var = _VarAdapter(self.alpha_matting)
        self.batch_limit_var = _VarAdapter(self.batch_limit)
        self.model_mode_var = _VarAdapter(self.model_name)

        # Estado de imágenes cargadas en memoria
        self.current_orig_pil: Optional[Image.Image] = None
        self.current_res_pil: Optional[Image.Image] = None

        # Servicios de procesamiento
        self.file_manager = FileManager(config)
        self.batch_service = BatchProcessingService(config, file_manager=self.file_manager)

        self.page: Optional[ft.Page] = page
        if self.page is not None:
            self._setup_page()

    def destroy(self):
        """Método de compatibilidad para finalización."""
        if self.page:
            try:
                self.page.window.close()
            except Exception:
                pass

    def _setup_page(self):
        """Configuración de ventana y tema de Flet."""
        page = self.page
        page.title = "Background Remover — Fondo Blanco Inteligente"
        page.theme_mode = ft.ThemeMode.DARK
        page.bgcolor = BG_DARK
        page.padding = 14
        page.scroll = ft.ScrollMode.AUTO

        # Configuración de ventana de escritorio
        page.window.width = 920
        page.window.height = 840
        page.window.min_width = 860
        page.window.min_height = 760
        page.window.resizable = True
        page.run_task(page.window.center)

        if ICON_ICO.exists():
            page.window.icon = str(ICON_ICO.resolve())

        self._build_ui()

    def _build_ui(self):
        page = self.page

        # FilePicker registrado como servicio del ciclo de vida (no como control visual en overlay)
        self.file_picker = ft.FilePicker()
        if self.file_picker not in page.services:
            page.services.append(self.file_picker)

        # 1. Header estilizado
        header = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("✨", size=22),
                            ft.Column(
                                controls=[
                                    ft.Text("Background Remover", size=16, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                    ft.Text("Remoción de fondo con IA | Fondo Blanco Inteligente", size=11, color=TEXT_MUTED),
                                ],
                                spacing=0,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Text("Desarrollado por Altikore", size=11, weight=ft.FontWeight.BOLD, color=ACCENT),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            bgcolor=SURFACE,
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=16, vertical=10),
            border=ft.Border.all(1, BORDER),
        )

        # 2. Tarjeta de Entrada y Rutas
        self.radio_mode = ft.RadioGroup(
            content=ft.Row(
                controls=[
                    ft.Radio(value="file", label="Archivo individual"),
                    ft.Radio(value="folder", label="Carpeta (Lote)"),
                ],
                spacing=16,
            ),
            value=self.mode,
            on_change=self._on_mode_change,
        )

        self.txt_input_path = ft.TextField(
            value=self.input_path,
            hint_text="Seleccione o examine una imagen o carpeta...",
            text_size=12,
            dense=True,
            expand=True,
            bgcolor=SURFACE_INNER,
            border_color=BORDER,
            on_change=self._on_input_text_change,
        )

        self.txt_output_path = ft.TextField(
            value=self.output_dir,
            hint_text="Carpeta de destino...",
            text_size=12,
            dense=True,
            expand=True,
            bgcolor=SURFACE_INNER,
            border_color=BORDER,
            on_change=self._on_output_text_change,
        )

        input_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("1. Modo y Rutas:", size=12, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            self.radio_mode,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text("Origen:", size=11, color=TEXT_MUTED, width=55),
                            self.txt_input_path,
                            ft.ElevatedButton(
                                "Examinar",
                                icon=ft.Icons.FOLDER_OPEN,
                                bgcolor=ACCENT,
                                color=TEXT_PRIMARY,
                                height=36,
                                on_click=self._browse_input,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    ft.Row(
                        controls=[
                            ft.Text("Destino:", size=11, color=TEXT_MUTED, width=55),
                            self.txt_output_path,
                            ft.ElevatedButton(
                                "Examinar",
                                icon=ft.Icons.FOLDER,
                                bgcolor=ACCENT,
                                color=TEXT_PRIMARY,
                                height=36,
                                on_click=self._browse_output,
                            ),
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                ],
                spacing=8,
            ),
            bgcolor=SURFACE,
            border_radius=8,
            padding=12,
            border=ft.Border.all(1, BORDER),
        )

        # 3. Tarjeta de Ajustes y Configuración
        self.color_swatch = ft.Container(
            width=18,
            height=18,
            bgcolor=self.bg_color_hex,
            border_radius=4,
            border=ft.Border.all(1, "#FFFFFF" if self.bg_color == "white" else BORDER),
        )

        self.radio_format = ft.RadioGroup(
            content=ft.Row(
                controls=[
                    ft.Radio(value="JPEG", label="JPEG"),
                    ft.Radio(value="PNG", label="PNG"),
                    ft.Radio(value="WEBP", label="WEBP"),
                ],
                spacing=10,
            ),
            value=self.output_format,
            on_change=self._on_format_change,
        )

        self.dropdown_model = ft.Dropdown(
            options=[
                ft.dropdown.Option("auto", "auto (SOTA Inteligente)"),
                ft.dropdown.Option("bria-rmbg", "bria-rmbg (Recomendado)"),
                ft.dropdown.Option("birefnet-general", "birefnet-general (Alta Fidelidad)"),
                ft.dropdown.Option("u2net_human_seg", "u2net_human_seg (Personas)"),
                ft.dropdown.Option("u2net", "u2net (General)"),
                ft.dropdown.Option("isnet-general-use", "isnet-general-use"),
                ft.dropdown.Option("silueta", "silueta (Ultra Rápido)"),
            ],
            value=self.model_name,
            text_size=11,
            dense=True,
            width=210,
            bgcolor=SURFACE_INNER,
            border_color=BORDER,
            on_select=self._on_model_change,
        )

        self.txt_batch_limit = ft.TextField(
            value=str(self.batch_limit),
            width=55,
            text_size=11,
            text_align=ft.TextAlign.CENTER,
            dense=True,
            bgcolor=SURFACE_INNER,
            border_color=BORDER,
            on_change=self._on_batch_limit_change,
        )

        self.chk_auto_crop = ft.Checkbox(
            label="Auto-crop",
            value=self.auto_crop,
            on_change=lambda e: setattr(self, "auto_crop", e.control.value),
        )

        self.chk_alpha_matting = ft.Checkbox(
            label="Alpha Matting",
            value=self.alpha_matting,
            on_change=lambda e: setattr(self, "alpha_matting", e.control.value),
        )

        settings_card = ft.Container(
            content=ft.Column(
                controls=[
                    # Fila 1: Color y Formato
                    ft.Row(
                        controls=[
                            ft.Row(
                                controls=[
                                    ft.Text("2. Ajustes:", size=12, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                                    ft.Text("Fondo:", size=11, color=TEXT_MUTED),
                                    self.color_swatch,
                                    ft.OutlinedButton("Blanco", height=30, on_click=lambda _: self._set_preset_color("white", "#FFFFFF")),
                                    ft.OutlinedButton("PNG Transp.", height=30, on_click=lambda _: self._set_preset_color("transparent", "#1E293B")),
                                    ft.OutlinedButton("Personalizado", height=30, on_click=self._open_custom_color_dialog),
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=8,
                            ),
                            ft.Row(
                                controls=[
                                    ft.Text("Formato:", size=11, color=TEXT_MUTED),
                                    self.radio_format,
                                ],
                                vertical_alignment=ft.CrossAxisAlignment.CENTER,
                                spacing=8,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    # Fila 2: Modelo + Checkboxes + Límite
                    ft.Row(
                        controls=[
                            ft.Text("Modelo IA:", size=11, color=TEXT_MUTED),
                            self.dropdown_model,
                            ft.Text("Límite:", size=11, color=TEXT_MUTED),
                            self.txt_batch_limit,
                            self.chk_auto_crop,
                            self.chk_alpha_matting,
                        ],
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                        spacing=12,
                    ),
                    # Fila Advertencia
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.Icon(ft.Icons.WARNING_AMBER_ROUNDED, color=WARNING, size=16),
                                ft.Text(
                                    "Estándar recomendado: 20 imágenes por intento. Puedes ampliar el límite según la capacidad de tu equipo.",
                                    size=10,
                                    weight=ft.FontWeight.W_500,
                                    color=WARNING,
                                ),
                            ],
                            spacing=6,
                        ),
                        bgcolor="#3D1A05",
                        border_radius=6,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                    ),
                ],
                spacing=8,
            ),
            bgcolor=SURFACE,
            border_radius=8,
            padding=12,
            border=ft.Border.all(1, BORDER),
        )

        # 4. Tarjeta de Previsualización Lado a Lado (Antes vs Después)
        self.img_orig_placeholder = ft.Column(
            controls=[
                ft.Icon(ft.Icons.IMAGE_OUTLINED, size=48, color=TEXT_MUTED),
                ft.Text("Seleccione una imagen\no presione Examinar", size=11, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.img_orig_view = ft.Image(
            src="",
            fit=ft.BoxFit.CONTAIN,
            visible=False,
            border_radius=6,
        )

        self.img_res_placeholder = ft.Column(
            controls=[
                ft.Icon(ft.Icons.AUTO_AWESOME_OUTLINED, size=48, color=TEXT_MUTED),
                ft.Text("Resultado procesado\naparecerá aquí", size=11, color=TEXT_MUTED, text_align=ft.TextAlign.CENTER),
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
        )

        self.img_res_view = ft.Image(
            src="",
            fit=ft.BoxFit.CONTAIN,
            visible=False,
            border_radius=6,
        )

        self.btn_copy_clipboard = ft.ElevatedButton(
            "📋 Copiar al Portapapeles",
            height=30,
            disabled=True,
            bgcolor="#1E3A5F",
            color=TEXT_PRIMARY,
            on_click=self._copy_result_to_clipboard,
        )

        preview_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Text("3. 👁️ Previsualización en Vivo — Antes vs. Después", size=12, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                            self.btn_copy_clipboard,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Row(
                        controls=[
                            # Contenedor Imagen Original
                            ft.Container(
                                content=ft.Column(
                                    controls=[
                                        ft.Text("Original", size=11, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
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
                                bgcolor=SURFACE_INNER,
                                border_radius=8,
                                padding=8,
                                expand=True,
                                height=240,
                                border=ft.Border.all(1, BORDER),
                            ),
                            # Contenedor Imagen Resultado
                            ft.Container(
                                content=ft.Column(
                                    controls=[
                                        ft.Text("Fondo Blanco / Resultado", size=11, weight=ft.FontWeight.BOLD, color=TEXT_MUTED),
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
                                bgcolor=SURFACE_INNER,
                                border_radius=8,
                                padding=8,
                                expand=True,
                                height=240,
                                border=ft.Border.all(1, BORDER),
                            ),
                        ],
                        spacing=12,
                    ),
                ],
                spacing=8,
            ),
            bgcolor=SURFACE,
            border_radius=8,
            padding=12,
            border=ft.Border.all(1, BORDER),
        )

        # 5. Barra de Estado del Modelo y Log de Ejecución
        self.lbl_model_status = ft.Text(
            "⚡ Selección automática activa: analiza cada imagen y aplica el modelo óptimo (SOTA RMBG).",
            size=11,
            color=TEXT_MUTED,
        )

        self.progress_bar = ft.ProgressBar(
            value=0.0,
            color=ACCENT,
            bgcolor="#1E3A5F",
            height=6,
            border_radius=3,
        )

        self.txt_log = ft.TextField(
            multiline=True,
            read_only=True,
            min_lines=3,
            max_lines=4,
            text_size=10,
            text_style=ft.TextStyle(font_family="Consolas"),
            bgcolor=SURFACE_INNER,
            border_color=BORDER,
            expand=True,
        )

        status_card = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=self.lbl_model_status,
                        bgcolor=SURFACE_INNER,
                        border_radius=6,
                        padding=ft.Padding.symmetric(horizontal=10, vertical=6),
                        border=ft.Border.all(1, BORDER),
                    ),
                    ft.Row(
                        controls=[
                            ft.Text("4. Registro de Estado:", size=11, weight=ft.FontWeight.BOLD, color=TEXT_PRIMARY),
                        ],
                    ),
                    self.progress_bar,
                    self.txt_log,
                ],
                spacing=6,
            ),
            bgcolor=SURFACE,
            border_radius=8,
            padding=12,
            border=ft.Border.all(1, BORDER),
        )

        # 6. Botones de Acción Inferiores
        self.btn_open_folder = ft.ElevatedButton(
            "📁 Abrir Carpeta Destino",
            height=38,
            bgcolor="#334155",
            color=TEXT_PRIMARY,
            on_click=self._open_output_folder,
        )

        self.btn_process = ft.ElevatedButton(
            "🚀 PROCESAR Y CAMBIAR A BLANCO",
            height=38,
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

        # Añadir todos los contenedores a la página
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
                spacing=10,
            )
        )

        self._log("Listo. Seleccione una imagen o carpeta y presione Procesar.")
        page.update()

    # ------------------------------------------------------------------
    # Previsualizaciones e imágenes
    # ------------------------------------------------------------------
    def _pil_to_base64(self, pil_img: Image.Image, max_size=(500, 300)) -> str:
        """Convierte una imagen PIL a base64 escalándola suavemente si es necesario."""
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
                self.page.update()
        except Exception as e:
            logger.debug(f"Error cargando thumbnail resultado: {e}")

    # ------------------------------------------------------------------
    # Manejadores de eventos y diálogos
    # ------------------------------------------------------------------
    def _on_mode_change(self, e):
        self.mode = e.control.value
        self.mode_var.set(self.mode)
        if self.mode == "file":
            self.txt_input_path.hint_text = "Seleccione una imagen (JPG, PNG, WEBP, HEIC, etc.)..."
        else:
            self.txt_input_path.hint_text = "Seleccione una carpeta con imágenes..."
        if self.page:
            self.page.update()

    def _on_input_text_change(self, e):
        self.input_path = e.control.value.strip()
        self.input_path_var.set(self.input_path)
        p = Path(self.input_path)
        if p.exists() and p.is_file():
            self._load_original_preview(p)

    def _on_output_text_change(self, e):
        self.output_dir = e.control.value.strip()
        self.output_dir_var.set(self.output_dir)

    def _on_format_change(self, e):
        self.output_format = e.control.value
        self.format_var.set(self.output_format)

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
            self.radio_format.value = "PNG"
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
        )

        color_presets = [
            ("#FFFFFF", "Blanco"),
            ("#F1F5F9", "Gris Suave"),
            ("#94A3B8", "Gris Medio"),
            ("#0F172A", "Negro Oscuro"),
            ("#EF4444", "Rojo"),
            ("#3B82F6", "Azul"),
            ("#10B981", "Verde"),
            ("#F59E0B", "Ámbar"),
        ]

        def pick_preset(hex_code):
            txt_custom_hex.value = hex_code
            if self.page:
                self.page.update()

        preset_chips = [
            ft.Container(
                content=ft.Text(label, size=10, color=TEXT_PRIMARY),
                bgcolor=SURFACE_INNER,
                border=ft.Border.all(1, hex_code),
                border_radius=4,
                padding=ft.Padding.symmetric(horizontal=8, vertical=4),
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
            title=ft.Text("Color de Fondo Personalizado", size=14, weight=ft.FontWeight.BOLD),
            content=ft.Column(
                controls=[
                    ft.Text("Seleccione un color predefinido o escriba el código hexadecimal:", size=11, color=TEXT_MUTED),
                    ft.Row(controls=preset_chips, wrap=True, spacing=6),
                    txt_custom_hex,
                ],
                spacing=10,
                tight=True,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.ElevatedButton("Aplicar", bgcolor=ACCENT, color=TEXT_PRIMARY, on_click=apply_color),
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
