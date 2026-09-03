"""
Pipelines de procesamiento para Background Remover Pro.
"""

from pipelines.standard import StandardPipeline
from pipelines.studio_layered import StudioLayeredPipeline

__all__ = [
    "StandardPipeline",
    "StudioLayeredPipeline",
]
