"""
Feature 3: AIS Vessel Attribution & Evidence Correlation Engine.
"""

from .schemas import (
    Feature2OriginContext,
    AISRecord,
    TrajectorySegment,
    ScoreBreakdown,
    RawEvidenceMetrics,
    VesselAttributionResult,
    Feature3EngineConfig,
    Feature3AttributionRequest,
    Feature3AttributionResponse,
)
from .engine import run_feature3_engine
from .adapter import extract_feature2_context

__all__ = [
    "Feature2OriginContext",
    "AISRecord",
    "TrajectorySegment",
    "ScoreBreakdown",
    "RawEvidenceMetrics",
    "VesselAttributionResult",
    "Feature3EngineConfig",
    "Feature3AttributionRequest",
    "Feature3AttributionResponse",
    "run_feature3_engine",
    "extract_feature2_context",
]
