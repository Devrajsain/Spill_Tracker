"""
Pydantic schemas for Feature 2 module.
"""

from .input_schema import CentroidCoordinates, GeoJSONGeometry, SlickDetectionInput
from .feature1_adapter import parse_feature1_input
from .output_schema import (
    CandidateOrigin,
    OriginCandidate,
    OriginAnalysisResult,
    OriginEstimationResult,
    ReleaseTimeWindowRange,
    ReleaseTimeWindow,
    SpatialUncertainty,
    ForecastStepResult,
    ForecastUncertainty,
    ForecastHorizonResult,
    ForecastAnalysisResult,
    Feature2PipelineResponse,
    ScientificDisclaimers,
)
from .simulation_schema import (
    Particle,
    ParticleState,
    Trajectory,
    ForwardSimulationResult,
    EnsembleStepStatistics,
    EnsembleSimulationResult,
    BackwardCandidateState,
    BackwardSimulationResult,
    BackwardCandidateEvaluationResult,
    ParticleEnsemble,
    EnvironmentalQueryWindow,
    AdvectionVector,
)
from ..data.domain import (
    SentinelObservationDomain,
    EnvironmentalQueryDomain,
)

__all__ = [
    "CentroidCoordinates",
    "GeoJSONGeometry",
    "SlickDetectionInput",
    "CandidateOrigin",
    "OriginCandidate",
    "OriginAnalysisResult",
    "OriginEstimationResult",
    "ReleaseTimeWindowRange",
    "ReleaseTimeWindow",
    "SpatialUncertainty",
    "ForecastStepResult",
    "ForecastUncertainty",
    "ForecastHorizonResult",
    "ForecastAnalysisResult",
    "Feature2PipelineResponse",
    "ScientificDisclaimers",
    "Particle",
    "ParticleState",
    "Trajectory",
    "ForwardSimulationResult",
    "EnsembleStepStatistics",
    "EnsembleSimulationResult",
    "BackwardCandidateState",
    "BackwardSimulationResult",
    "BackwardCandidateEvaluationResult",
    "ParticleEnsemble",
    "EnvironmentalQueryWindow",
    "AdvectionVector",
    "SentinelObservationDomain",
    "EnvironmentalQueryDomain",
]
