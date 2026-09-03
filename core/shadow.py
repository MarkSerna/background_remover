"""
Generador de sombras de contacto realistas (Contact Shadow & Ambient Occlusion).
Crea sombras sintéticas de alta calidad con desenfoque anisotrópico elíptico
y decaimiento morfológico en la base de contacto de los objetos.
"""

from typing import Tuple, Optional, Union
import numpy as np
from PIL import Image, ImageFilter
from scipy.ndimage import gaussian_filter


class ContactShadowGenerator:
    """
    Genera sombras de contacto suaves y realistas (Ambient Occlusion)
    en la base de objetos o sujetos segmentados.
    """

    def __init__(
        self,
        intensity: float = 0.65,
        blur_radius: float = 12.0,
        vertical_scale: float = 0.28,
        offset_y: int = 4,
        color: Tuple[int, int, int] = (20, 24, 30),
    ):
        """
        Args:
            intensity: Opacidad máxima de la sombra (0.0 a 1.0).
            blur_radius: Radio base de difusión gaussiana.
            vertical_scale: Factor de compresión vertical para perspectiva de suelo (0.1 a 0.5).
            offset_y: Desplazamiento vertical hacia abajo en píxeles.
            color: Color RGB de la sombra (por defecto negro azulado neutro).
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
        Genera una capa RGBA con la sombra de contacto sobre un lienzo transparente.

        Args:
            mask: Máscara alfa del objeto (PIL en modo 'L' o array 2D numpy).
            canvas_size: Dimensiones (ancho, alto) del lienzo. Si no se indica, usa el tamaño de la máscara.
            custom_intensity: Sobrescribe la intensidad para esta instancia.
            custom_blur: Sobrescribe el radio de desenfoque.

        Returns:
            Image.Image en modo RGBA con la sombra proyectada.
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

        # Detectar el punto de contacto inferior (base del objeto)
        active_y, active_x = np.where(mask_arr > 0.15)
        if len(active_y) == 0:
            # Máscara vacía, retornar imagen transparente
            return Image.new("RGBA", (out_w, out_h), (0, 0, 0, 0))

        y_min, y_max = active_y.min(), active_y.max()
        x_min, x_max = active_x.min(), active_x.max()
        obj_height = max(1, y_max - y_min)
        obj_width = max(1, x_max - x_min)

        # 1. Capa de Oclusión de Contacto Inmediato (Hard Core Contact)
        # Extraer los píxeles del tercio inferior del objeto
        lower_threshold_y = int(y_max - obj_height * 0.18)
        base_mask = np.zeros_like(mask_arr)
        base_mask[lower_threshold_y:y_max+1, :] = mask_arr[lower_threshold_y:y_max+1, :]

        # Proyectar elípticamente aplastando verticalmente
        base_img = Image.fromarray((base_mask * 255).astype(np.uint8), mode="L")
        scaled_h = max(4, int(obj_height * self.vertical_scale))
        scaled_w = int(obj_width * 1.05)

        squashed = base_img.resize((scaled_w, scaled_h), Image.Resampling.BILINEAR)

        # Crear canvas para la sombra
        shadow_canvas = Image.new("L", (width, height), 0)
        paste_x = max(0, x_min - int(obj_width * 0.025))
        paste_y = min(height - scaled_h, y_max - int(scaled_h * 0.3) + self.offset_y)
        shadow_canvas.paste(squashed, (paste_x, paste_y))

        # 2. Doble filtrado gaussiano:
        # a) Sombra densa de contacto (borde fino)
        core_shadow = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=max(2.0, blur * 0.25)))
        core_arr = np.array(core_shadow, dtype=np.float32) / 255.0 * 0.75

        # b) Penumbra suave ambiental (difusión amplia)
        soft_shadow = shadow_canvas.filter(ImageFilter.GaussianBlur(radius=blur))
        soft_arr = np.array(soft_shadow, dtype=np.float32) / 255.0 * 0.45

        # Combinar oclusión ambiental compuesta
        combined_alpha = np.clip((core_arr + soft_arr) * intensity, 0.0, 1.0)

        # Restar suavemente la máscara original para que la sombra no oscurezca el interior del objeto
        combined_alpha = np.clip(combined_alpha - (mask_arr * 0.4), 0.0, 1.0)

        # Renderizar en RGBA
        alpha_uint8 = (combined_alpha * 255).astype(np.uint8)
        r, g, b = self.color
        r_chan = np.full((height, width), r, dtype=np.uint8)
        g_chan = np.full((height, width), g, dtype=np.uint8)
        b_chan = np.full((height, width), b, dtype=np.uint8)

        rgba_arr = np.dstack([r_chan, g_chan, b_chan, alpha_uint8])
        shadow_rgba = Image.fromarray(rgba_arr, mode="RGBA")

        if (width, height) != (out_w, out_h):
            shadow_rgba = shadow_rgba.resize((out_w, out_h), Image.Resampling.BILINEAR)

        return shadow_rgba
