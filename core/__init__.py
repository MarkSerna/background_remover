"""
Módulos principales del motor de segmentación y composición de estudio.
"""

from core.segmenter import BiRefNetSegmenter
from core.detector import ZeroShotDetector
from core.depth import DepthEstimator
from core.shadow import ContactShadowGenerator
from core.compositor import LayeredCompositor

__all__ = [
    "BiRefNetSegmenter",
    "ZeroShotDetector",
    "DepthEstimator",
    "ContactShadowGenerator",
    "LayeredCompositor",
]
