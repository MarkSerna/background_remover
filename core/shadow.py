"""
Generador de sombras de contacto realistas (Contact Shadow & Ambient Occlusion).
Crea sombras sintéticas de alta fidelidad con mapeo de oclusión ambiental (Ambient Occlusion)
directamente bajo el borde de contacto inferior de cada objeto con el plano del suelo.
"""

from typing import Tuple, Optional, Union
import numpy as np
from PIL import Image, ImageFilter
from scipy.ndimage import gaussian_filter


class ContactShadowGenerator:
    """
    Genera sombras de contacto suaves y oclusión ambiental (Ambient Occlusion)
    precisamente ancladas bajo el borde inferior de apoyo de los objetos.
    """

    def __init__(
        self,
        intensity: float = 0.65,
        blur_radius: float = 12.0,
        vertical_scale: float = 0.22,
        offset_y: int = 2,
        color: Tuple[int, int, int] = (18, 22, 28),
    ):
        """
        Args:
            intensity: Opacidad máxima de la sombra (0.0 a 1.0).
            blur_radius: Radio base de difusión gaussiana.
            vertical_scale: Factor de compresión vertical para perspectiva de suelo.
            offset_y: Desplazamiento vertical hacia abajo en píxeles.
            color: Color RGB de la sombra (por defecto negro neutro de estudio).
        """
        self.intensity = max(0.0, min(1.0, intensity))
        self.blur_radius = max(1.0, blur_radius)
        self.vertical_scale = max(0.05, min(1.0, vertical_scale))
        self.offset_y = offset_y
        self.color = color

    def generate(
        self,
        mask: Union[Image.Image, np.ndarray],
        canvas_size: Optional[Tuple[int, int]] = None,
        custom_intensity: Optional[float] = None,
        custom_blur: Optional[float] = None,
    ) -> Image.Image:
        """
        Genera una capa RGBA con la sombra de oclusión ambiental directamente
        bajo la base del objeto que apoya en el plano del suelo.

        Args:
            mask: Máscara alfa del objeto (PIL en modo 'L' o array 2D numpy).
            canvas_size: Dimensiones (ancho, alto) del lienzo.
            custom_intensity: Sobrescribe la intensidad para esta instancia.
            custom_blur: Sobrescribe el radio de desenfoque.

        Returns:
            Image.Image en modo RGBA con la sombra proyectada sobre fondo transparente.
        """
        if isinstance(mask, Image.Image):
            if mask.mode != "L":
                mask = mask.convert("L")
            mask_arr = np.array(mask, dtype=np.float32) / 255.0
            width, height = mask.size
        else:
            mask_arr = np.array(mask, dtype=np.float32)
            if mask_arr.max() > 1.0:
                mask_arr /= 255.0
            height, width = mask_arr.shape

        target_size = canvas_size if canvas_size is not None else (width, height)
        out_w, out_h = target_size

        intensity = custom_intensity if custom_intensity is not None else self.intensity
        blur = custom_blur if custom_blur is not None else self.blur_radius

        # Detectar el punto de contacto inferior (base de apoyo del objeto)
        active_y, active_x = np.where(mask_arr > 0.15)
        if len(active_y) == 0:
            return Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))

        y_min, y_max = int(active_y.min()), int(active_y.max())
        x_min, x_max = int(active_x.min()), int(active_x.max())
        obj_height = max(1, y_max - y_min)
        obj_width = max(1, x_max - x_min)

        # -------------------------------------------------------------
        # 1. Huella de Contacto Directo (Footprint Ambient Occlusion)
        # Extraer la huella inferior exacta donde el objeto toca el suelo
        # -------------------------------------------------------------
        footprint_thickness = max(2, int(obj_height * 0.08))
        lower_band_y = max(y_min, y_max - footprint_thickness)

        footprint_mask = np.zeros_like(mask_arr)
        footprint_mask[lower_band_y:y_max+1, :] = mask_arr[lower_band_y:y_max+1, :]

        # Escalamiento elíptico anisotrópico anclado exactamente en la línea del suelo
        fp_img = Image.fromarray((footprint_mask * 255).astype(np.uint8), mode="L")
        scaled_h = max(4, int(obj_height * self.vertical_scale))
        scaled_w = int(obj_width * 1.08)

        squashed_fp = fp_img.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)

        # Canvas para la oclusión ambiental
        ao_canvas = Image.new("L", (width, height), 0)
        paste_x = max(0, min(width - scaled_w, x_min - int(obj_width * 0.04)))
        paste_y = max(0, min(height - scaled_h, y_max - int(scaled_h * 0.45) + self.offset_y))
        ao_canvas.paste(squashed_fp, (paste_x, paste_y))

        # -------------------------------------------------------------
        # 2. Doble difusión: Oclusión Dura (contacto) + Penumbra Difusa
        # -------------------------------------------------------------
        # Capa 1: Oclusión ultra-cercana (contacto físico inmediato)
        core_blur = max(1.5, blur * 0.20)
        core_layer = ao_canvas.filter(ImageFilter.GaussianBlur(radius=core_blur))
        core_arr = np.array(core_layer, dtype=np.float32) / 255.0 * 0.85

        # Capa 2: Penumbra difusa suave extendida en el suelo
        penumbra_layer = ao_canvas.filter(ImageFilter.GaussianBlur(radius=blur))
        penumbra_arr = np.array(penumbra_layer, dtype=np.float32) / 255.0 * 0.40

        # Combinar ambas capas
        combined_shadow = np.clip((core_arr + penumbra_arr) * intensity, 0.0, 1.0)

        # Substraer suavemente la silueta interior del objeto para que la sombra
        # se proyecte exclusivamente en el suelo exterior
        combined_shadow = np.clip(combined_shadow - (mask_arr * 0.50), 0.0, 1.0)

        # Renderizar en capa RGBA
        alpha_uint8 = (combined_shadow * 255).astype(np.uint8)
        r, g, b = self.color
        r_chan = np.full((height, width), r, dtype=np.uint8)
        g_chan = np.full((height, width), g, dtype=np.uint8)
        b_chan = np.full((height, width), b, dtype=np.uint8)

        rgba_arr = np.dstack([r_chan, g_chan, b_chan, alpha_uint8])
        shadow_rgba = Image.fromarray(rgba_arr, mode="RGBA")

        if (width, height) != (out_w, out_h):
            shadow_rgba = shadow_rgba.resize((out_w, out_h), Image.Resampling.BILINEAR)

        return shadow_rgba
