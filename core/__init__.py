"""
Módulos principales del motor de segmentación, mejora fotográfica y composición de estudio.
"""

from core.segmenter import BiRefNetSegmenter
from core.detector import ZeroShotDetector
from core.depth import DepthEstimator
from core.shadow import ContactShadowGenerator
from core.compositor import LayeredCompositor
from core.enhancer import StudioEnhancer

__all__ = [
    "BiRefNetSegmenter",
    "ZeroShotDetector",
    "DepthEstimator",
    "ContactShadowGenerator",
    "LayeredCompositor",
    "StudioEnhancer",
]
