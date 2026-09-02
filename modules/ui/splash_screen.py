"""
Splash Screen ligero y moderno para Background Remover.
Muestra de forma inmediata (< 50 ms) una ventana visual con barra de progreso
determinada (0% - 100%) y estado en tiempo real para indicar exactamente cuándo iniciará la app.
"""
import sys
import tkinter as tk
from pathlib import Path


def _base_path() -> Path:
    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).parent.parent.parent


class SplashScreen:
    WIDTH = 480
    HEIGHT = 380
    BG = "#0B132B"
    SURFACE = "#1E293B"
    ACCENT = "#3B82F6"
    ACCENT_LIGHT = "#60A5FA"
    ACCENT_GLOW = "#93C5FD"
    TEXT_MUTED = "#94A3B8"

    def __init__(self):
        self._alive = True
        self._after_id = None
        self._target_progress = 0.05
        self._current_progress = 0.0
        self._root = tk.Tk()
        self._root.overrideredirect(True)
        self._root.attributes("-topmost", True)
        self._root.configure(bg=self.BG)
        self._root.resizable(False, False)

        sw = self._root.winfo_screenwidth()
        sh = self._root.winfo_screenheight()
        x = (sw - self.WIDTH) // 2
        y = (sh - self.HEIGHT) // 2
        self._root.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")

        self._build_content()
        self._root.update()
        self._after_id = self._root.after(20, self._animate_bar)

    def _build_content(self):
        # Marco principal con borde estilizado
        main_frame = tk.Frame(self._root, bg=self.BG, highlightbackground="#1E3A8A", highlightthickness=1)
        main_frame.pack(fill="both", expand=True)

        # 1. Imagen del Splash con Logo de Altikore
        splash_path = _base_path() / "assets" / "splash.png"
        self._photo = None
        if splash_path.exists():
            try:
                self._photo = tk.PhotoImage(file=str(splash_path))
                img_lbl = tk.Label(main_frame, image=self._photo, bg=self.BG, bd=0, highlightthickness=0)
                img_lbl.pack(fill="x", pady=(0, 2))
            except Exception:
                self._photo = None

        if self._photo is None:
            # Fallback nativo si no se encuentra splash.png
            tk.Label(main_frame, text="✨", bg=self.BG, fg=self.ACCENT,
                     font=("Segoe UI", 36)).pack(pady=(16, 2))
            tk.Label(main_frame, text="Background Remover", bg=self.BG,
                     fg="white", font=("Segoe UI", 18, "bold")).pack()
            tk.Label(main_frame, text="Fondo Blanco Inteligente con IA", bg=self.BG,
                     fg=self.ACCENT_LIGHT, font=("Segoe UI", 10)).pack(pady=(2, 4))
            tk.Label(main_frame, text="Desarrollado por Altikore", bg=self.BG,
                     fg=self.TEXT_MUTED, font=("Segoe UI", 9, "bold")).pack(pady=(0, 8))

        # 2. Panel inferior: Estado, Porcentaje y Barra de Progreso Determinada
        bottom_frame = tk.Frame(main_frame, bg=self.BG)
        bottom_frame.pack(fill="x", side="bottom", padx=20, pady=(0, 14))

        # Fila de texto de estado y porcentaje
        status_row = tk.Frame(bottom_frame, bg=self.BG)
        status_row.pack(fill="x", pady=(0, 4))

        self._status_label = tk.Label(
            status_row,
            text="Iniciando Background Remover...",
            bg=self.BG,
            fg=self.TEXT_MUTED,
            font=("Segoe UI", 9),
            anchor="w"
        )
        self._status_label.pack(side="left")

        self._percent_label = tk.Label(
            status_row,
            text="0%",
            bg=self.BG,
            fg=self.ACCENT_LIGHT,
            font=("Segoe UI", 9, "bold"),
            anchor="e"
        )
        self._percent_label.pack(side="right")

        # Barra de progreso moderna con track
        bar_bg = tk.Frame(bottom_frame, bg=self.SURFACE, height=8)
        bar_bg.pack(fill="x", pady=(2, 4))
        bar_bg.pack_propagate(False)

        self._bar = tk.Canvas(bar_bg, bg=self.SURFACE, height=8, highlightthickness=0, bd=0)
        self._bar.pack(fill="both", expand=True)

        # Pie de página
        footer_row = tk.Frame(bottom_frame, bg=self.BG)
        footer_row.pack(fill="x", pady=(2, 0))

        tk.Label(
            footer_row,
            text="Desarrollado por Altikore",
            bg=self.BG,
            fg="#475569",
            font=("Segoe UI", 8),
            anchor="w"
        ).pack(side="left")

        tk.Label(
            footer_row,
            text="v1.0.0",
            bg=self.BG,
            fg="#475569",
            font=("Segoe UI", 8),
            anchor="e"
        ).pack(side="right")

    def set_progress(self, fraction: float, text: str = None):
        """
        Actualiza el progreso determinado (0.0 a 1.0) y el mensaje de estado opcional.
        """
        if not self._alive:
            return
        try:
            self._target_progress = max(0.0, min(1.0, float(fraction)))
            if text:
                self._status_label.configure(text=text)
            self._root.update_idletasks()
        except Exception:
            pass

    def set_status(self, text: str):
        """Actualiza el mensaje de estado."""
        if not self._alive:
            return
        try:
            self._status_label.configure(text=text)
            self._root.update_idletasks()
        except Exception:
            pass

    def _animate_bar(self):
        if not self._alive:
            return
        try:
            # Interpolación suave hacia el progreso objetivo
            diff = self._target_progress - self._current_progress
            if abs(diff) > 0.002:
                self._current_progress += diff * 0.22
            else:
                self._current_progress = self._target_progress

            c = self._bar
            w = c.winfo_width() or (self.WIDTH - 40)
            fill_w = max(0, int(w * self._current_progress))

            c.delete("all")
            # Fondo del track
            c.create_rectangle(0, 0, w, 8, fill=self.SURFACE, outline="")
            
            if fill_w > 0:
                # Barra principal de progreso
                c.create_rectangle(0, 0, fill_w, 8, fill=self.ACCENT, outline="")
                # Brillo superior
                c.create_rectangle(0, 0, fill_w, 3, fill=self.ACCENT_LIGHT, outline="")
                # Punta brillante del indicador
                if fill_w > 4:
                    c.create_rectangle(fill_w - 4, 0, fill_w, 8, fill=self.ACCENT_GLOW, outline="")

            # Actualizar etiqueta de porcentaje
            pct_val = int(round(self._current_progress * 100))
            self._percent_label.configure(text=f"{pct_val}%")

            self._root.update_idletasks()
            if self._alive:
                self._after_id = self._root.after(20, self._animate_bar)
        except tk.TclError:
            pass

    def run(self):
        """Inicia el bucle de eventos del splash."""
        if self._alive:
            self._root.mainloop()

    def close(self):
        """Cierra y destruye la ventana del splash de forma segura."""
        self._alive = False
        if self._after_id is not None:
            try:
                self._root.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None
        try:
            self._root.destroy()
        except Exception:
            pass


