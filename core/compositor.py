"""
Compositor estratificado multicapa en orden de profundidad Z.
Realiza composición fotográfica precisa (Back-to-Front) combinando
capas de objetos, sombras de contacto, fondo con gradiente de horizonte
de estudio y preservación de perspectiva espacial.
"""

from typing import List, Dict, Any, Tuple, Optional, Union
import numpy as np
from PIL import Image

from core.shadow import ContactShadowGenerator


class LayeredCompositor:
    """
    Compositor multicapa con ordenamiento Z-index, gradiente de ciclorama
    y fusión de sombras de oclusión ambiental.
    """

    def __init__(
        self,
        shadow_generator: Optional[ContactShadowGenerator] = None,
        default_bg: str = "white",
        use_ground_gradient: bool = True,
    ):
        """
        Args:
            shadow_generator: Instancia de ContactShadowGenerator para proyectar sombras.
            default_bg: Fondo por defecto ("white", "transparent", o código Hex "#FFFFFF").
            use_ground_gradient: Si es True, aplica un sutil degradado de horizonte (#FFFFFF a #F4F4F4).
        """
        self.shadow_generator = shadow_generator or ContactShadowGenerator()
        self.default_bg = default_bg
        self.use_ground_gradient = use_ground_gradient

    def _create_ground_gradient_canvas(self, size: Tuple[int, int]) -> Image.Image:
        """
        Crea un lienzo con degradado de horizonte de ciclorama de estudio:
        - Parte superior (cielo/fondo infinito): #FFFFFF (255, 255, 255)
        - Transición suave hacia el plano del suelo: gradiente lineal hasta #F4F4F4 (244, 244, 244)
        """
        w, h = size
        horizon_y = int(h * 0.50)  # La mitad superior se mantiene blanco puro

        canvas_arr = np.full((h, w, 4), 255, dtype=np.uint8)

        # Gradiente desde horizon_y hasta h
        floor_height = h - horizon_y
        if floor_height > 0:
            # Atenuación desde 255 (#FFFFFF) hasta 244 (#F4F4F4)
            gradient_v = np.linspace(255.0, 244.0, floor_height, dtype=np.float32)
            gradient_grid = np.repeat(gradient_v[:, np.newaxis], w, axis=1).astype(np.uint8)

            canvas_arr[horizon_y:, :, 0] = gradient_grid
            canvas_arr[horizon_y:, :, 1] = gradient_grid
            canvas_arr[horizon_y:, :, 2] = gradient_grid

        return Image.fromarray(canvas_arr, mode="RGBA")

    def _parse_bg_color(
        self,
        bg: str,
        size: Tuple[int, int],
        apply_gradient: bool = True,
    ) -> Image.Image:
        """Crea el lienzo base según la especificación del fondo."""
        w, h = size
        bg_lower = bg.strip().lower()

        if bg_lower == "transparent":
            return Image.new("RGBA", (w, h), (0, 0, 0, 0))
        elif bg_lower in ("white", "blanco", "#ffffff"):
            if apply_gradient:
                return self._create_ground_gradient_canvas(size)
            return Image.new("RGBA", (w, h), (255, 255, 255, 255))
        elif bg_lower.startswith("#") and len(bg_lower) in (4, 7):
            hex_val = bg_lower.lstrip("#")
            if len(hex_val) == 3:
                hex_val = "".join(c * 2 for c in hex_val)
            r = int(hex_val[0:2], 16)
            g = int(hex_val[2:4], 16)
            b = int(hex_val[4:6], 16)
            return Image.new("RGBA", (w, h), (r, g, b, 255))
        else:
            if apply_gradient:
                return self._create_ground_gradient_canvas(size)
            return Image.new("RGBA", (w, h), (255, 255, 255, 255))

    def composite(
        self,
        layers: List[Dict[str, Any]],
        canvas_size: Tuple[int, int],
        bg_color: Optional[str] = None,
        apply_shadows: bool = True,
        use_ground_gradient: Optional[bool] = None,
        shadow_intensity: Optional[float] = None,
        shadow_blur: Optional[float] = None,
    ) -> Tuple[Image.Image, List[Dict[str, Any]]]:
        """
        Combina las capas de instancias en orden de profundidad Z (Back-to-Front)
        con sombras de oclusión ambiental y fondo de horizonte de estudio.

        Args:
            layers: Lista de diccionarios de capas ('rgba', 'mask', 'depth', 'label').
            canvas_size: (ancho, alto) del lienzo final.
            bg_color: Color de fondo ("white", "transparent", o Hex).
            apply_shadows: Si es True, proyecta sombras de oclusión de contacto.
            use_ground_gradient: Si es True, activa el degradado de suelo #FFFFFF -> #F4F4F4.
            shadow_intensity: Sobrescribe la intensidad de la sombra.
            shadow_blur: Sobrescribe el radio de desenfoque.

        Returns:
            Tuple con (Imagen final PIL, Lista de metadatos de las capas ordenadas)
        """
        bg_spec = bg_color if bg_color is not None else self.default_bg
        grad_enabled = use_ground_gradient if use_ground_gradient is not None else self.use_ground_gradient

        canvas = self._parse_bg_color(bg_spec, canvas_size, apply_gradient=grad_enabled)

        if not layers:
            if bg_spec.lower() != "transparent":
                canvas = canvas.convert("RGB")
            return canvas, []

        # Ordenar capas: menor profundidad Z primero (fondo), mayor profundidad al final (primer plano)
        sorted_layers = sorted(layers, key=lambda l: l.get("depth", 0.0))

        processed_metadata = []

        for z_idx, layer in enumerate(sorted_layers):
            rgba = layer.get("rgba")
            mask = layer.get("mask")
            depth = layer.get("depth", 0.0)
            label = layer.get("label", f"layer_{z_idx}")

            if rgba is None:
                continue

            if rgba.size != canvas_size:
                rgba = rgba.resize(canvas_size, Image.Resampling.LANCZOS)

            # 1. Proyectar sombra de oclusión ambiental (Ambient Contact Shadow)
            if apply_shadows and mask is not None:
                shadow_layer = self.shadow_generator.generate(
                    mask=mask,
                    canvas_size=canvas_size,
                    custom_intensity=shadow_intensity,
                    custom_blur=shadow_blur,
                )
                canvas = Image.alpha_composite(canvas, shadow_layer)

            # 2. Componer la capa del objeto
            if rgba.mode != "RGBA":
                rgba = rgba.convert("RGBA")
            canvas = Image.alpha_composite(canvas, rgba)

            processed_metadata.append({
                "z_index": z_idx,
                "label": label,
                "depth": depth,
                "bbox": layer.get("bbox"),
            })

        # Si el fondo no es transparente, convertir a RGB para guardado eficiente
        if bg_spec.lower() != "transparent":
            canvas = canvas.convert("RGB")

        return canvas, processed_metadata
