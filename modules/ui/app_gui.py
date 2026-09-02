"""
Interfaz Grafica avanzada con CustomTkinter para Background Remover.
Incluye:
  - Drag & Drop (arrastrar y soltar imagenes/carpetas)
  - Vista previa en vivo Antes vs Despues (Side-by-side thumbnails)
  - Copiar imagen procesada al portapapeles de Windows (1 clic)
  - Icono corporativo personalizado
  - Persistencia de preferencias en AppData
  - Diseño moderno sin scroll
"""

import os
import sys
import io
import threading
import logging
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps
import customtkinter as ctk
from tkinter import filedialog, messagebox


try:
    import win32clipboard
    HAS_CLIPBOARD = True
except Exception:
    HAS_CLIPBOARD = False

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    class CTkWithDnD(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.TkdndVersion = TkinterDnD._require(self)
    HAS_DND = True
except Exception:
    HAS_DND = False
    CTkWithDnD = ctk.CTk

from modules.models.config import config
from modules.models.settings_manager import settings_manager
from modules.services.batch_service import BatchProcessingService
from modules.services.file_manager import FileManager
from modules.utils.helpers import parse_color_string

logger = logging.getLogger(__name__)

# Apariencia global
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

ACCENT = "#3B82F6"
ACCENT_HOVER = "#2563EB"
SUCCESS = "#22C55E"
WARNING = "#F59E0B"
DANGER = "#EF4444"
SURFACE = "#1E293B"
CARD = "#0F172A"
TEXT_MUTED = "#94A3B8"

ICON_ICO = Path("assets/app_icon.ico")
ICON_PNG = Path("assets/app_icon.png")


class BackgroundRemoverGUI(CTkWithDnD):
    """Ventana principal avanzada con Drag & Drop, Previsualización y Copiado al Portapapeles."""

    def __init__(self):
        super().__init__()
        self.title("Background Remover — Fondo Blanco Inteligente")
        self.geometry("860x760")
        self.minsize(820, 720)
        self.configure(fg_color=CARD)

        # Cargar icono corporativo
        self._setup_icon()

        # Cargar preferencias guardadas desde AppData
        saved_output = settings_manager.get("output_dir", "")
        default_out = saved_output if saved_output and Path(saved_output).exists() else str(config.output_dir.resolve())

        self.mode_var = ctk.StringVar(value="file")
        self.input_path_var = ctk.StringVar(value="")
        self.output_dir_var = ctk.StringVar(value=default_out)
        self.bg_color_var = ctk.StringVar(value=settings_manager.get("bg_color", "white"))
        self.bg_color_hex = settings_manager.get("bg_color_hex", "#FFFFFF")
        self.format_var = ctk.StringVar(value=settings_manager.get("output_format", "JPEG"))
        self.auto_crop_var = ctk.BooleanVar(value=settings_manager.get("auto_crop", False))
        self.alpha_matting_var = ctk.BooleanVar(value=settings_manager.get("alpha_matting", False))
        self.batch_limit_var = ctk.IntVar(value=settings_manager.get("batch_limit", config.processing.batch_limit))
        self.model_mode_var = ctk.StringVar(value=settings_manager.get("model_name", "auto"))
        self.is_processing = False

        # Imagenes cargadas para previsualizacion
        self.current_orig_pil: Optional[Image.Image] = None
        self.current_res_pil: Optional[Image.Image] = None

        # Servicios
        self.file_manager = FileManager(config)
        self.batch_service = BatchProcessingService(config, file_manager=self.file_manager)

        self._build_ui()

        # Configurar Drag & Drop
        if HAS_DND:
            self._setup_dnd()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_icon(self):
        """Establece el icono de la ventana."""
        try:
            if ICON_ICO.exists():
                self.iconbitmap(str(ICON_ICO.resolve()))
        except Exception:
            pass

    def _setup_dnd(self):
        """Habilita la funcion de arrastrar y soltar archivos/carpetas sobre la ventana."""
        try:
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._on_drop_files)
        except Exception as e:
            logger.debug(f"No se pudo registrar Drag & Drop: {e}")

    def _on_drop_files(self, event):
        """Responde al soltar archivos o carpetas en la ventana."""
        raw_data = event.data.strip()
        # En Windows tkinterdnd envuelve rutas con espacios entre llaves {C:/Ruta Con Espacio}
        if raw_data.startswith("{") and raw_data.endswith("}"):
            path_str = raw_data[1:-1]
        else:
            path_str = raw_data.split()[0] if raw_data else ""
        
        p = Path(path_str)
        if p.exists():
            if p.is_file():
                self.mode_var.set("file")
                self._on_mode_change()
                self.input_path_var.set(str(p.resolve()))
                self._load_original_preview(p)
                self._log(f"📥 Archivo arrastrado: {p.name}")
            elif p.is_dir():
                self.mode_var.set("folder")
                self._on_mode_change()
                self.input_path_var.set(str(p.resolve()))
                self._log(f"📁 Carpeta arrastrada: {p.name}")

    def _build_ui(self):
        main_container = ctk.CTkFrame(self, fg_color=CARD, corner_radius=0)
        main_container.pack(fill="both", expand=True, padx=12, pady=8)

        # 1. Header compacto
        header = ctk.CTkFrame(main_container, fg_color=SURFACE, corner_radius=8, height=42)
        header.pack(fill="x", pady=(0, 4))
        header.pack_propagate(False)

        h_inner = ctk.CTkFrame(header, fg_color="transparent")
        h_inner.pack(fill="both", expand=True, padx=12, pady=4)

        ctk.CTkLabel(
            h_inner,
            text="✨ Background Remover",
            font=ctk.CTkFont(family="Segoe UI", size=15, weight="bold"),
            text_color="white",
        ).pack(side="left")

        ctk.CTkLabel(
            h_inner,
            text="Remoción de fondo con IA | Soporta Drag & Drop, Previsualización y Copiado al Portapapeles",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=TEXT_MUTED,
        ).pack(side="left", padx=(12, 0))

        ctk.CTkLabel(
            h_inner,
            text="Desarrollado por Altikore",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=ACCENT,
        ).pack(side="right")


        # 2. Sección Superior: Rutas y Ajustes (fila única, ancho completo)
        cfg_card = ctk.CTkFrame(main_container, fg_color=SURFACE, corner_radius=8)
        cfg_card.pack(fill="x", pady=2)

        # Fila Modo y Rutas
        mode_row = ctk.CTkFrame(cfg_card, fg_color="transparent")
        mode_row.pack(fill="x", padx=10, pady=(6, 2))

        ctk.CTkLabel(mode_row, text="1. Entrada:", font=ctk.CTkFont(size=11, weight="bold"), text_color="white").pack(side="left", padx=(0, 10))
        ctk.CTkRadioButton(mode_row, text="Archivo", variable=self.mode_var, value="file", command=self._on_mode_change,
                           font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(side="left", padx=(0, 10))
        ctk.CTkRadioButton(mode_row, text="Carpeta (Lote)", variable=self.mode_var, value="folder", command=self._on_mode_change,
                           font=ctk.CTkFont(size=11), fg_color=ACCENT, hover_color=ACCENT_HOVER).pack(side="left")

        in_row = ctk.CTkFrame(cfg_card, fg_color="transparent")
        in_row.pack(fill="x", padx=10, pady=2)
        in_row.grid_columnconfigure(1, weight=1)
        self.input_label = ctk.CTkLabel(in_row, text="Origen:", width=55, anchor="w", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED)
        self.input_label.grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(in_row, textvariable=self.input_path_var, placeholder_text="Arrastre imagen/carpeta o examine...",
                     font=ctk.CTkFont(size=11), height=26, fg_color="#0B132B", border_color="#334155").grid(row=0, column=1, sticky="ew", padx=4)
        self.btn_browse_input = ctk.CTkButton(in_row, text="Examinar", width=75, height=26, font=ctk.CTkFont(size=11),
                                              fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._browse_input)
        self.btn_browse_input.grid(row=0, column=2)

        out_row = ctk.CTkFrame(cfg_card, fg_color="transparent")
        out_row.pack(fill="x", padx=10, pady=(2, 4))
        out_row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(out_row, text="Destino:", width=55, anchor="w", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).grid(row=0, column=0, sticky="w")
        ctk.CTkEntry(out_row, textvariable=self.output_dir_var, placeholder_text="Carpeta de salida...",
                     font=ctk.CTkFont(size=11), height=26, fg_color="#0B132B", border_color="#334155").grid(row=0, column=1, sticky="ew", padx=4)
        self.btn_browse_output = ctk.CTkButton(out_row, text="Examinar", width=75, height=26, font=ctk.CTkFont(size=11),
                                               fg_color=ACCENT, hover_color=ACCENT_HOVER, command=self._browse_output)
        self.btn_browse_output.grid(row=0, column=2)

        # Separador interno
        ctk.CTkFrame(cfg_card, fg_color="#334155", height=1).pack(fill="x", padx=10, pady=2)

        # Fila Ajustes 1: Fondo y Formato
        cfg_row1 = ctk.CTkFrame(cfg_card, fg_color="transparent")
        cfg_row1.pack(fill="x", padx=10, pady=(4, 2))
        ctk.CTkLabel(cfg_row1, text="2. Ajustes:", font=ctk.CTkFont(size=11, weight="bold"), text_color="white").pack(side="left", padx=(0, 8))
        ctk.CTkLabel(cfg_row1, text="Fondo:", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(side="left", padx=(0, 4))
        self.color_swatch = ctk.CTkLabel(cfg_row1, text="", width=16, height=16, fg_color=self.bg_color_hex, corner_radius=3)
        self.color_swatch.pack(side="left", padx=(0, 4))
        ctk.CTkButton(cfg_row1, text="Color", width=50, height=22, font=ctk.CTkFont(size=10),
                      fg_color="#334155", hover_color="#475569", command=self._choose_color).pack(side="left", padx=1)
        ctk.CTkButton(cfg_row1, text="Blanco", width=50, height=22, font=ctk.CTkFont(size=10),
                      fg_color="#334155", hover_color="#475569", command=lambda: self._set_preset_color("white", "#FFFFFF")).pack(side="left", padx=1)
        ctk.CTkButton(cfg_row1, text="PNG Transp.", width=75, height=22, font=ctk.CTkFont(size=10),
                      fg_color="#334155", hover_color="#475569", command=lambda: self._set_preset_color("transparent", "#1E293B")).pack(side="left", padx=(1, 8))

        ctk.CTkLabel(cfg_row1, text="Formato:", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(side="left", padx=(0, 4))
        for fmt in ["JPEG", "PNG", "WEBP"]:
            ctk.CTkRadioButton(cfg_row1, text=fmt, value=fmt, variable=self.format_var,
                               fg_color=ACCENT, hover_color=ACCENT_HOVER, font=ctk.CTkFont(size=10)).pack(side="left", padx=2)

        # Fila Ajustes 2: Modelo + Checkboxes
        cfg_row2 = ctk.CTkFrame(cfg_card, fg_color="transparent")
        cfg_row2.pack(fill="x", padx=10, pady=(2, 4))
        ctk.CTkLabel(cfg_row2, text="Modelo IA:", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(side="left", padx=(0, 4))
        models = ["auto", "bria-rmbg", "birefnet-general", "u2net_human_seg", "u2net", "isnet-general-use", "silueta"]
        self.model_menu = ctk.CTkOptionMenu(
            cfg_row2, variable=self.model_mode_var, values=models,
            font=ctk.CTkFont(size=10), fg_color="#0B132B", button_color=ACCENT,
            button_hover_color=ACCENT_HOVER, dropdown_fg_color=SURFACE, width=130, height=24,
        )
        self.model_menu.pack(side="left", padx=(0, 8))

        ctk.CTkLabel(cfg_row2, text="Límite:", font=ctk.CTkFont(size=11), text_color=TEXT_MUTED).pack(side="left", padx=(0, 2))
        self.spin_limit = ctk.CTkEntry(cfg_row2, textvariable=self.batch_limit_var, width=48, height=24, font=ctk.CTkFont(size=10), justify="center")
        self.spin_limit.pack(side="left", padx=(0, 8))

        ctk.CTkCheckBox(cfg_row2, text="Auto-crop", variable=self.auto_crop_var,
                        fg_color=ACCENT, hover_color=ACCENT_HOVER, font=ctk.CTkFont(size=10)).pack(side="left", padx=(0, 6))
        ctk.CTkCheckBox(cfg_row2, text="Alpha Matting", variable=self.alpha_matting_var,
                        fg_color=ACCENT, hover_color=ACCENT_HOVER, font=ctk.CTkFont(size=10)).pack(side="left")

        # Fila Advertencia
        warn_row = ctk.CTkFrame(cfg_card, fg_color="#451A03", corner_radius=4)
        warn_row.pack(fill="x", padx=10, pady=(2, 6))
        ctk.CTkLabel(
            warn_row,
            text="  ⚠️ Estándar recomendado: 20 imágenes por intento. Puedes ampliar el límite según la capacidad de tu equipo.",
            font=ctk.CTkFont(size=10, weight="bold"), text_color=WARNING, anchor="w",
        ).pack(fill="x", padx=4, pady=2)

        # 3. Previsualización en Vivo (altura FIJA — no varía al cargar imágenes)
        prev_card = ctk.CTkFrame(main_container, fg_color=SURFACE, corner_radius=8, height=300)
        prev_card.pack(fill="x", pady=2)
        prev_card.pack_propagate(False)  # <-- impide que las imágenes redimensionen el panel

        prev_header_row = ctk.CTkFrame(prev_card, fg_color="transparent")
        prev_header_row.pack(fill="x", padx=10, pady=(6, 4))
        ctk.CTkLabel(
            prev_header_row, text="3. 👁️ Previsualización en Vivo — Antes vs. Después",
            font=ctk.CTkFont(size=11, weight="bold"), text_color="white",
        ).pack(side="left")
        self.btn_copy_clipboard = ctk.CTkButton(
            prev_header_row, text="📋 Copiar al Portapapeles", height=24,
            font=ctk.CTkFont(size=10, weight="bold"),
            fg_color="#1E3A5F", hover_color=ACCENT,
            command=self._copy_result_to_clipboard, state="disabled"
        )
        self.btn_copy_clipboard.pack(side="right")

        prev_box = ctk.CTkFrame(prev_card, fg_color="transparent")
        prev_box.pack(fill="both", expand=True, padx=8, pady=(0, 6))
        prev_box.grid_columnconfigure(0, weight=1)
        prev_box.grid_columnconfigure(1, weight=1)
        prev_box.grid_rowconfigure(0, weight=1)

        # Marco Original (altura fija interna)
        orig_frame = ctk.CTkFrame(prev_box, fg_color="#0B132B", corner_radius=8)
        orig_frame.grid(row=0, column=0, sticky="nsew", padx=(2, 4), pady=2)
        orig_frame.grid_propagate(False)  # fija el marco
        ctk.CTkLabel(orig_frame, text="Original", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED).pack(pady=(6, 2))
        self.lbl_preview_orig = ctk.CTkLabel(
            orig_frame, text="Arrastre una imagen\no presione Examinar",
            font=ctk.CTkFont(size=11), text_color="#475569", anchor="center"
        )
        self.lbl_preview_orig.pack(expand=True)

        # Marco Resultado (altura fija interna)
        res_frame = ctk.CTkFrame(prev_box, fg_color="#0B132B", corner_radius=8)
        res_frame.grid(row=0, column=1, sticky="nsew", padx=(4, 2), pady=2)
        res_frame.grid_propagate(False)  # fija el marco
        ctk.CTkLabel(res_frame, text="Fondo Blanco / Resultado", font=ctk.CTkFont(size=11, weight="bold"), text_color=TEXT_MUTED).pack(pady=(6, 2))
        self.lbl_preview_res = ctk.CTkLabel(
            res_frame, text="Procesando...",
            font=ctk.CTkFont(size=11), text_color="#475569", anchor="center"
        )
        self.lbl_preview_res.pack(expand=True)

        # 4. Barra de Estado del Modelo IA (compacta, debajo del preview)
        self.model_info_frame = ctk.CTkFrame(main_container, fg_color="#0C1A2E", corner_radius=6, height=26)
        self.model_info_frame.pack(fill="x", pady=(2, 1))
        self.model_info_frame.pack_propagate(False)
        self.model_info_label = ctk.CTkLabel(
            self.model_info_frame,
            text="  ⚡ Selección automática activa: analiza cada imagen y aplica el modelo óptimo (SOTA RMBG).",
            font=ctk.CTkFont(size=10), text_color=TEXT_MUTED, anchor="w",
        )
        self.model_info_label.pack(fill="both", expand=True, padx=8)

        # 5. Log de actividad compacto (franja fija debajo de la barra de estado)
        log_card = ctk.CTkFrame(main_container, fg_color=SURFACE, corner_radius=8, height=90)
        log_card.pack(fill="x", pady=(1, 2))
        log_card.pack_propagate(False)

        log_header = ctk.CTkFrame(log_card, fg_color="transparent")
        log_header.pack(fill="x", padx=8, pady=(4, 0))
        ctk.CTkLabel(
            log_header, text="4. Registro de Estado:",
            font=ctk.CTkFont(size=10, weight="bold"), text_color="white"
        ).pack(side="left")

        self.progress_bar = ctk.CTkProgressBar(
            log_card, mode="determinate", height=6,
            fg_color="#1E3A5F", progress_color=ACCENT, corner_radius=4
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x", padx=8, pady=(2, 2))

        self.log_box = ctk.CTkTextbox(
            log_card, font=ctk.CTkFont(family="Consolas", size=10),
            fg_color=CARD, text_color="#CBD5E1", corner_radius=4,
            border_color="#1E3A5F", border_width=1, state="disabled"
        )
        self.log_box.pack(fill="both", expand=True, padx=8, pady=(0, 4))

        # 6. Barra de Acciones Inferior
        actions = ctk.CTkFrame(main_container, fg_color="transparent")
        actions.pack(fill="x", pady=(2, 0))
        actions.grid_columnconfigure(1, weight=1)

        self.btn_open_folder = ctk.CTkButton(
            actions, text="📁 Abrir Carpeta Destino", width=170, height=34,
            font=ctk.CTkFont(size=11), fg_color="#334155", hover_color="#475569",
            command=self._open_output_folder,
        )
        self.btn_open_folder.grid(row=0, column=0, sticky="w")

        self.btn_process = ctk.CTkButton(
            actions, text="🚀 PROCESAR Y CAMBIAR A BLANCO", height=34,
            font=ctk.CTkFont(size=12, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            command=self._start_processing_thread,
        )
        self.btn_process.grid(row=0, column=1, sticky="e")

        self._log("Listo. Arrastre una imagen/carpeta o presione Examinar y Procesar.")

    # ------------------------------------------------------------------
    # Previsualización e imágenes
    # ------------------------------------------------------------------
    # Panel fijo 300px | header ~32px | título ~26px | márgenes ~12px → imagen disponible ≈ 215px alto
    _PREVIEW_SIZE = (380, 215)

    def _load_original_preview(self, img_path: Path):
        """Carga y muestra el thumbnail de la imagen original escalado al panel fijo."""
        try:
            pil_img = Image.open(img_path)
            pil_img = ImageOps.exif_transpose(pil_img)
            self.current_orig_pil = pil_img
            thumb = self._make_ctk_image(pil_img, size=self._PREVIEW_SIZE)
            self.lbl_preview_orig.configure(image=thumb, text="")
        except Exception as e:
            logger.debug(f"Error cargando thumbnail original: {e}")

    def _update_result_preview(self, result_path: Path):
        """Carga y muestra el thumbnail del resultado procesado escalado al panel fijo."""
        try:
            pil_img = Image.open(result_path)
            self.current_res_pil = pil_img
            thumb = self._make_ctk_image(pil_img, size=self._PREVIEW_SIZE)
            self.lbl_preview_res.configure(image=thumb, text="")
            if HAS_CLIPBOARD:
                self.btn_copy_clipboard.configure(state="normal")
        except Exception as e:
            logger.debug(f"Error cargando thumbnail resultado: {e}")

    @staticmethod
    def _make_ctk_image(pil_img: Image.Image, size=(380, 215)) -> ctk.CTkImage:
        """Crea un CTkImage escalado proporcionalmente para caber en 'size' sin recortar."""
        w, h = pil_img.size
        ratio = min(size[0] / w, size[1] / h)
        new_size = (max(1, int(w * ratio)), max(1, int(h * ratio)))
        return ctk.CTkImage(light_image=pil_img, dark_image=pil_img, size=new_size)

    def _copy_result_to_clipboard(self):
        """Copia la imagen procesada resultante al portapapeles de Windows."""
        if not HAS_CLIPBOARD or self.current_res_pil is None:
            messagebox.showwarning("Atención", "No hay imagen procesada disponible para copiar.")
            return
        try:
            out = io.BytesIO()
            self.current_res_pil.convert("RGB").save(out, "BMP")
            data = out.getvalue()[14:]  # Omitir cabecera BMP de 14 bytes
            out.close()

            win32clipboard.OpenClipboard()
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
            win32clipboard.CloseClipboard()

            messagebox.showinfo("Copiado", "¡Imagen copiada al portapapeles de Windows! Puedes pegarla directamente con Ctrl+V.")
            self._log("📋 Imagen copiada al portapapeles de Windows (Ctrl+V listo).")
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo copiar al portapapeles: {e}")

    # ------------------------------------------------------------------
    # Eventos y acciones
    # ------------------------------------------------------------------
    def _on_mode_change(self):
        if self.mode_var.get() == "file":
            self.input_label.configure(text="Origen:")
        else:
            self.input_label.configure(text="Carpeta:")

    def _browse_input(self):
        if self.mode_var.get() == "file":
            path = filedialog.askopenfilename(
                title="Seleccionar imagen",
                filetypes=[
                    ("Imágenes compatibles", "*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.tiff;*.heic;*.heif;*.HEIC;*.HEIF"),
                    ("Fotos Apple HEIC/HEIF", "*.heic;*.heif;*.HEIC;*.HEIF"),
                    ("Todos los archivos", "*.*")
                ]
            )
            if path:
                p = Path(path)
                self.input_path_var.set(str(p.resolve()))

                self._load_original_preview(p)
        else:
            path = filedialog.askdirectory(title="Seleccionar carpeta con imágenes")
            if path:
                self.input_path_var.set(path)

    def _browse_output(self):
        path = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if path:
            self.output_dir_var.set(path)

    def _choose_color(self):
        from tkinter import colorchooser
        color = colorchooser.askcolor(title="Seleccionar Color de Fondo", initialcolor=self.bg_color_hex)
        if color and color[1]:
            self.bg_color_hex = color[1]
            self.bg_color_var.set(color[1])
            self.color_swatch.configure(fg_color=self.bg_color_hex)

    def _set_preset_color(self, name: str, hex_val: str):
        self.bg_color_var.set(name)
        self.bg_color_hex = hex_val
        self.color_swatch.configure(fg_color=hex_val)
        if name == "transparent":
            self.format_var.set("PNG")

    def _open_output_folder(self):
        out = Path(self.output_dir_var.get() or "output")
        out.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(out.resolve()))
        except Exception as e:
            messagebox.showerror("Error", f"No se pudo abrir la carpeta: {e}")

    def _log(self, msg: str):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"{msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _update_model_info(self, result):
        if result is None:
            self.model_info_label.configure(
                text="  Modelo manual seleccionado.",
                text_color=TEXT_MUTED,
            )
            return
        pct = f"{result.confidence:.0%}"
        txt = f"  🎯 Modelo aplicado: {result.model_name} ({pct} confianza) — {result.reason}"
        self.model_info_label.configure(text=txt, text_color=SUCCESS)

    def _set_ui_state(self, processing: bool):
        self.is_processing = processing
        state = "disabled" if processing else "normal"
        self.btn_process.configure(state=state)
        self.btn_browse_input.configure(state=state)
        self.btn_browse_output.configure(state=state)

    def _start_processing_thread(self):
        if self.is_processing:
            return

        input_str = self.input_path_var.get().strip()
        output_str = self.output_dir_var.get().strip()

        if not input_str:
            messagebox.showwarning("Atención", "Por favor seleccione una imagen o carpeta de origen.")
            return
        if not output_str:
            messagebox.showwarning("Atención", "Por favor seleccione una carpeta de destino.")
            return

        input_path = Path(input_str)
        if not input_path.exists():
            messagebox.showerror("Error", f"La ruta de entrada no existe:\n{input_path}")
            return

        model_choice = self.model_mode_var.get()
        self.batch_service.config.processing.model_name = model_choice
        self._save_user_preferences()

        self._set_ui_state(True)
        self.progress_bar.set(0)
        self.model_info_label.configure(text="  ⏳ Analizando imagen y ejecutando IA...", text_color=TEXT_MUTED)

        t = threading.Thread(target=self._run_processing, args=(input_path, Path(output_str)), daemon=True)
        t.start()

    def _run_processing(self, input_path: Path, output_dir: Path):
        output_dir.mkdir(parents=True, exist_ok=True)
        bg_color = self.bg_color_var.get()
        out_format = self.format_var.get()
        auto_crop = self.auto_crop_var.get()
        alpha_matting = self.alpha_matting_var.get()
        self.batch_service.config.processing.alpha_matting = alpha_matting
        self.batch_service.config.processing.output_format = out_format

        if input_path.is_file():
            self.after(0, lambda: self._load_original_preview(input_path))
            self._log(f"\n--- Procesando: {input_path.name} ---")
            self.progress_bar.set(0.3)
            success, out_path, err = self.batch_service.process_single_image(
                input_path=input_path,
                output_path=self.file_manager.determine_output_path(input_path, output_dir=output_dir, output_format=out_format),
                bg_color=bg_color, output_format=out_format, auto_crop=auto_crop,
            )
            self.progress_bar.set(1.0)
            sel = self.batch_service.remover.last_selection
            self.after(0, lambda s=sel: self._update_model_info(s))

            if success:
                self.after(0, lambda p=out_path: self._update_result_preview(p))
                self._log(f"[OK] Guardado: {out_path.name}")
                self.after(0, lambda: messagebox.showinfo("Completado", f"¡Imagen procesada con éxito!\nGuardada en: {out_path}"))
            else:
                self._log(f"[ERROR] {err}")
                self.after(0, lambda: messagebox.showerror("Error", f"No se pudo procesar:\n{err}"))

        elif input_path.is_dir():
            images = self.file_manager.get_input_images(input_path)
            total_found = len(images)

            if total_found == 0:
                self._log("[AVISO] No se encontraron imágenes compatibles.")
                self.after(0, lambda: messagebox.showwarning("Sin Imágenes", "No se encontraron imágenes compatibles."))
                self.after(0, lambda: self._set_ui_state(False))
                return

            try:
                raw_limit = self.batch_limit_var.get()
                limit = int(raw_limit) if int(raw_limit) > 0 else 20
            except Exception:
                limit = 20

            if total_found > limit:
                self._log(f"[AVISO] {total_found} imágenes detectadas. Procesando primeras {limit} según el límite configurado.")
                images = images[:limit]

            total = len(images)
            self._log(f"\n--- Lote: {total} imágenes (límite: {limit}) ---")
            ok = fail = 0

            for idx, img in enumerate(images, 1):
                self._log(f"[{idx}/{total}] {img.name}...")
                self.after(0, lambda p=img: self._load_original_preview(p))
                dest = self.file_manager.determine_output_path(img, output_dir=output_dir, output_format=out_format)
                success, out_path, err = self.batch_service.process_single_image(
                    input_path=img, output_path=dest,
                    bg_color=bg_color, output_format=out_format, auto_crop=auto_crop,
                )
                if success:
                    ok += 1
                    sel = self.batch_service.remover.last_selection
                    self.after(0, lambda s=sel: self._update_model_info(s))
                    self.after(0, lambda p=out_path: self._update_result_preview(p))
                    self._log(f"   -> [OK] {out_path.name}")
                else:
                    fail += 1
                    self._log(f"   -> [FALLO] {err}")
                self.after(0, lambda v=idx/total: self.progress_bar.set(v))

            self._log(f"\n[FINALIZADO] Exitosas: {ok}/{total} | Fallidas: {fail}/{total}")
            self.after(0, lambda: messagebox.showinfo(
                "Lote Finalizado",
                f"Proceso por lotes finalizado:\n• Exitosas: {ok}\n• Fallidas: {fail}\n\nGuardadas en: {output_dir}"
            ))

        self.after(0, lambda: self._set_ui_state(False))

    def _save_user_preferences(self):
        """Guarda las preferencias actuales en AppData."""
        try:
            settings_manager.save_settings({
                "output_dir": self.output_dir_var.get().strip(),
                "bg_color": self.bg_color_var.get(),
                "bg_color_hex": self.bg_color_hex,
                "output_format": self.format_var.get(),
                "auto_crop": self.auto_crop_var.get(),
                "alpha_matting": self.alpha_matting_var.get(),
                "batch_limit": self.batch_limit_var.get(),
                "model_name": self.model_mode_var.get(),
            })
        except Exception as e:
            logger.debug(f"No se pudieron guardar preferencias: {e}")

    def _on_close(self):
        """Manejador de cierre de ventana."""
        self._save_user_preferences()
        self.destroy()


def launch_gui() -> None:
    """Punto de entrada de la interfaz gráfica."""
    app = BackgroundRemoverGUI()
    app.mainloop()


if __name__ == "__main__":
    launch_gui()
