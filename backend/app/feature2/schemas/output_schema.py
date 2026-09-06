"""
Output data models for Feature 2: Origin estimation and Future slick prediction.
Follows scientific integrity rules: non-calibrated relative confidence scores,
uncertainty regions rather than definitive single points, and explicit disclaimers.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator
from .input_schema import CentroidCoordinates, GeoJSONGeometry


class ReleaseTimeWindow(BaseModel):
    """Estimated candidate release time window with bounds."""
    earliest_utc: datetime = Field(
        ...,
        description="Earliest plausible release time boundary."
    )
    latest_utc: datetime = Field(
        ...,
        description="Latest plausible release time boundary."
    )
    peak_evidence_utc: datetime = Field(
        ...,
        description="Release timestamp exhibiting peak trajectory convergence / evidence."
    )
    window_duration_hours: float = Field(
        ...,
        ge=0.0,
        description="Duration of the estimated release window in hours."
    )


class SpatialUncertainty(BaseModel):
    """Spatial uncertainty bounds for candidate origin or forecast position."""
    semi_major_axis_km: float = Field(
        ...,
        ge=0.0,
        description="Estimated semi-major axis of the 95% spatial dispersion ellipse in km."
    )
    semi_minor_axis_km: float = Field(
        ...,
        ge=0.0,
        description="Estimated semi-minor axis of the 95% spatial dispersion ellipse in km."
    )
    orientation_deg: float = Field(
        ...,
        ge=0.0,
        le=360.0,
        description="Orientation of the major axis in degrees clockwise from North."
    )
    uncertainty_polygon: GeoJSONGeometry = Field(
        ...,
        description="GeoJSON Polygon representation of the spatial uncertainty boundary."
    )


class CandidateOrigin(BaseModel):
    """
    Estimated candidate spill origin region.
    IMPORTANT: Represents a probabilistic convergence zone, not an exact point.
    """
    cluster_id: int = Field(
        ...,
        description="Index or identifier for this origin candidate cluster."
    )
    estimated_centroid: CentroidCoordinates = Field(
        ...,
        description="Centroid coordinates of the candidate origin convergence region."
    )
    spatial_uncertainty: SpatialUncertainty = Field(
        ...,
        description="Spatial dispersion and uncertainty boundary for this candidate origin."
    )
    release_time_window: ReleaseTimeWindow = Field(
        ...,
        description="Estimated temporal window during which the release likely took place."
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Relative model evidence score (0.0 to 1.0), NOT a calibrated frequentist probability."
    )
    particle_support_ratio: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Fraction of backtracked particle trajectories converging into this region."
    )
    environmental_consistency_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Consistency metric between reverse trajectory flow and environmental gradient history."
    )

    @property
    def evidence_score(self) -> float:
        """Alias for confidence_score emphasizing non-calibrated model evidence semantics."""
        return self.confidence_score


class ScientificDisclaimers(BaseModel):
    """Explicit scientific notices describing assumptions, limitations, and interpretation rules."""
    methodology: str = Field(
        default="Lagrangian inverse trajectory reconstruction & forward hydrodynamic advection.",
        description="Summary of the physics engine methodology."
    )
    confidence_score_definition: str = Field(
        default="Relative evidence score based on trajectory convergence and environmental consistency, NOT a calibrated probability.",
        description="Definition of the confidence score."
    )
    uncertainty_notice: str = Field(
        default="Origin positions and future slick locations are estimated spatial zones with associated dispersion bounds.",
        description="Spatial uncertainty notice."
    )
    limitations: List[str] = Field(
        default_factory=lambda: [
            "Backward advection assumes hydrodynamic field reversibility under turbulent diffusion approximations.",
            "Weathering processes (evaporation, emulsification, dissolution) are not fully coupled to initial position estimates.",
            "Sub-grid turbulence and unresolved coastal bathymetry may introduce spatial displacement bias.",
            "Environmental data resolution (temporal and spatial) constrains trajectory precision."
        ],
        description="Known scientific constraints and limitations."
    )


class OriginCandidate(BaseModel):
    """
    Estimated origin candidate region from backward reconstructed particle convergence (Task 3D).
    Represents an uncalibrated relative evidence score and spatial dispersion zone.
    """
    candidate_id: str = Field(..., description="Unique identifier for this origin candidate (e.g. ORIGIN_1).")
    cluster_id: int = Field(0, description="Spatial cluster index.")
    release_time: datetime = Field(..., description="Candidate release timestamp (UTC).")
    latitude: float = Field(..., description="Candidate centroid latitude.")
    longitude: float = Field(..., description="Candidate centroid longitude.")
    candidate_score: float = Field(..., ge=0.0, le=1.0, description="Uncalibrated relative confidence/evidence score.")
    convergence_score: float = Field(..., ge=0.0, le=1.0, description="Spatial compactness / convergence evidence score.")
    trajectory_score: float = Field(..., ge=0.0, le=1.0, description="Trajectory continuity and validity score.")
    coverage_score: float = Field(..., ge=0.0, le=1.0, description="Environmental data coverage score.")
    uncertainty_radius_km: float = Field(..., ge=0.0, description="Ensemble dispersion uncertainty radius in km.")
    active_particle_count: int = Field(..., ge=0, description="Number of active particles supporting this candidate.")
    total_particle_count: int = Field(..., ge=0, description="Total particles simulated in this candidate state.")
    cluster_fraction: float = Field(1.0, ge=0.0, le=1.0, description="Fraction of active particles belonging to this cluster.")
    covariance_matrix: List[List[float]] = Field(default_factory=list, description="2x2 spatial covariance matrix in local meters.")
    semi_major_axis_km: Optional[float] = None
    semi_minor_axis_km: Optional[float] = None
    orientation_deg: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def evidence_score(self) -> float:
        """Alias for candidate_score emphasizing non-calibrated model evidence semantics."""
        return self.candidate_score


class ReleaseTimeWindowRange(BaseModel):
    """Estimated candidate release time window with start and end bounds."""
    start: datetime = Field(..., description="Earliest plausible release time boundary (UTC).")
    end: datetime = Field(..., description="Latest plausible release time boundary (UTC).")
    peak_evidence_time: Optional[datetime] = Field(None, description="Release timestamp exhibiting peak trajectory evidence.")
    duration_hours: Optional[float] = Field(None, ge=0.0, description="Duration of window in hours.")


class OriginEstimationResult(BaseModel):
    """Complete backward origin estimation and candidate ranking result."""
    spill_id: str
    observation_time: datetime
    search_horizon_hours: float
    best_candidate: Optional[OriginCandidate] = None
    candidates: List[OriginCandidate] = Field(default_factory=list)
    release_time_window: Optional[ReleaseTimeWindowRange] = None
    disclaimers: ScientificDisclaimers = Field(default_factory=ScientificDisclaimers)


class OriginAnalysisResult(BaseModel):
    """Complete backward / inverse reconstruction result."""
    spill_id: str
    observation_time: datetime
    search_horizon_hours: float
    candidate_origins: List[CandidateOrigin] = Field(
        default_factory=list,
        description="Ranked list of candidate origin regions."
    )
    origin_estimation: Optional[OriginEstimationResult] = Field(
        default=None,
        description="Complete Task 3D origin estimation result."
    )
    best_candidate: Optional[OriginCandidate] = Field(
        default=None,
        description="Highest ranked candidate origin."
    )
    candidates: List[OriginCandidate] = Field(
        default_factory=list,
        description="Detailed Task 3D origin candidates."
    )
    release_time_window: Optional[ReleaseTimeWindowRange] = Field(
        default=None,
        description="Estimated release time window."
    )
    disclaimers: ScientificDisclaimers = Field(default_factory=ScientificDisclaimers)


class ForecastStepResult(BaseModel):
    """Forecast state at a specific future lead time horizon."""
    lead_time_hours: float = Field(..., description="Forecast lead time relative to T0 (e.g. 6.0, 12.0, 24.0, 48.0).")
    forecast_time_utc: datetime = Field(..., description="Target future UTC timestamp.")
    predicted_centroid: CentroidCoordinates = Field(..., description="Predicted slick centroid at target time.")
    predicted_slick_polygon: GeoJSONGeometry = Field(..., description="Predicted slick contour boundary.")
    spatial_uncertainty: SpatialUncertainty = Field(..., description="Forecast dispersion uncertainty ellipse/polygon.")
    mean_drift_speed_kmh: float = Field(..., ge=0.0, description="Mean drift velocity magnitude in km/h.")
    mean_drift_direction_deg: float = Field(..., ge=0.0, le=360.0, description="Mean drift direction in degrees from North.")


class ForecastUncertainty(BaseModel):
    """Uncertainty representation for forecast horizon."""
    radius_km: float = Field(..., ge=0.0, description="Ensemble dispersion spread radius in km.")
    semi_major_km: float = Field(..., ge=0.0, description="Semi-major axis of covariance uncertainty ellipse in km.")
    semi_minor_km: float = Field(..., ge=0.0, description="Semi-minor axis of covariance uncertainty ellipse in km.")
    orientation_deg: float = Field(..., ge=0.0, le=360.0, description="Orientation of major axis in degrees from North.")
    uncertainty_polygon: Optional[GeoJSONGeometry] = Field(None, description="Optional GeoJSON polygon of the uncertainty ellipse.")


class ForecastHorizonResult(BaseModel):
    """Forecast state at a specific future lead time horizon (Task 3E)."""
    lead_time_hours: float = Field(..., description="Forecast lead time in hours (e.g. 6.0, 12.0, 24.0, 48.0).")
    forecast_time: datetime = Field(..., description="Target future UTC timestamp.")
    valid: bool = Field(True, description="Whether forecast horizon has sufficient environmental coverage and active particles.")
    reason: Optional[str] = Field(None, description="Explanation if forecast horizon is marked invalid.")
    centroid: CentroidCoordinates = Field(..., description="Predicted slick centroid at target time.")
    uncertainty: ForecastUncertainty = Field(..., description="Predicted spatial dispersion uncertainty.")
    covariance_matrix: List[List[float]] = Field(default_factory=list, description="2x2 metric covariance matrix in meters.")
    active_particle_count: int = Field(..., ge=0, description="Number of active particles at this horizon.")
    total_particle_count: int = Field(..., ge=0, description="Total seeded particles in simulation.")
    active_fraction: float = Field(..., ge=0.0, le=1.0, description="Fraction of particles remaining active and within domain.")
    quality: str = Field("high", description="Forecast data/model quality indicator: 'high', 'medium', or 'low'.")
    mean_drift_speed_kmh: Optional[float] = Field(None, ge=0.0, description="Mean drift speed from T0 in km/h.")
    mean_drift_direction_deg: Optional[float] = Field(None, ge=0.0, le=360.0, description="Mean drift direction from T0 in degrees from North.")
    predicted_slick_polygon: Optional[GeoJSONGeometry] = Field(None, description="Optional predicted slick contour polygon.")

    @property
    def predicted_centroid(self) -> CentroidCoordinates:
        return self.centroid

    @property
    def forecast_time_utc(self) -> datetime:
        return self.forecast_time


class ForecastAnalysisResult(BaseModel):
    """Complete forward forecast trajectory result."""
    spill_id: str
    observation_time: datetime
    horizons: List[ForecastStepResult] = Field(
        default_factory=list,
        description="Legacy list of forecast step results."
    )
    forecast: Dict[str, ForecastHorizonResult] = Field(
        default_factory=dict,
        description="Horizon-keyed forecast dictionary (e.g. {'6h': ..., '12h': ..., '24h': ..., '48h': ...})."
    )
    origin_candidate_id: Optional[str] = Field(None, description="Optional origin candidate hypothesis ID if conditioned.")
    provenance: Dict[str, Any] = Field(default_factory=dict, description="Environmental data sources and provenance.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Simulation parameters and execution metadata.")
    disclaimers: ScientificDisclaimers = Field(default_factory=ScientificDisclaimers)


class Feature2PipelineResponse(BaseModel):
    """Consolidated end-to-end response combining backward origin tracing and forward forecasting."""
    feature2_version: str = Field(default="1.0.0", description="Feature 2 pipeline specification version.")
    spill_id: str
    observation_time: Optional[datetime] = None
    execution_time_utc: datetime = Field(default_factory=datetime.utcnow)
    origin_estimation: Optional[OriginEstimationResult] = None
    origin_analysis: Optional[OriginAnalysisResult] = None
    forecast: Dict[str, ForecastHorizonResult] = Field(
        default_factory=dict,
        description="Forward forecast keyed by lead time (e.g. {'6h': ..., '12h': ..., '24h': ..., '48h': ...})."
    )
    forecast_analysis: Optional[ForecastAnalysisResult] = None
    disclaimers: ScientificDisclaimers = Field(default_factory=ScientificDisclaimers)

    # Unified Contract Fields (Task 5)
    observation: Optional["ObservationOutputSummary"] = None
    environment: Optional["EnvironmentOutputSummary"] = None
    origin: Optional["OriginOutputSummary"] = None
    forecast_summary: Optional["ForecastOutputSummary"] = None
    quality: Optional["QualityAssessmentSummary"] = None
    reproducibility: Optional["ReproducibilitySummary"] = None

    def to_unified_result(self) -> "UnifiedFeature2Result":
        """Converts response into the unified, audit-ready Feature 2 result contract."""
        if not (self.observation and self.environment and self.origin and self.forecast_summary and self.quality and self.reproducibility):
            raise ValueError("Cannot convert to UnifiedFeature2Result: one or more unified contract sections are missing.")
        return UnifiedFeature2Result(
            feature2_version=self.feature2_version,
            spill_id=self.spill_id,
            observation=self.observation,
            environment=self.environment,
            origin=self.origin,
            forecast=self.forecast_summary,
            quality=self.quality,
            reproducibility=self.reproducibility,
            disclaimers=self.disclaimers,
        )


class LatLonCoord(BaseModel):
    """Geographic coordinate pair."""
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees.")
    lon: float = Field(..., ge=-180.0, le=360.0, description="Longitude in decimal degrees.")


class ObservationOutputSummary(BaseModel):
    """Observation metadata derived directly from Feature 1 Sentinel-1 SAR detection."""
    observation_time: datetime = Field(..., description="Satellite overpass / observation timestamp (UTC).")
    centroid: LatLonCoord = Field(..., description="Observed slick centroid.")
    geometry: GeoJSONGeometry = Field(..., description="Observed slick polygon boundary from SAR.")
    area_km2: float = Field(..., ge=0.0, description="Estimated surface area of observed slick in square kilometers.")
    perimeter_km: Optional[float] = Field(None, ge=0.0, description="Estimated slick perimeter in kilometers.")


class BoundingBoxSummary(BaseModel):
    """Spatial bounding box bounds."""
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


class EnvironmentDomainSummary(BaseModel):
    """Dynamically derived environmental query domain."""
    bbox: BoundingBoxSummary
    buffer_km: float = Field(50.0, description="Geodetic buffer distance in kilometers.")


class TimeWindowSummary(BaseModel):
    """Spacetime temporal interval boundaries."""
    start: datetime
    end: datetime


class EnvironmentalFieldProvenance(BaseModel):
    """Machine-readable provenance for an individual environmental forcing field."""
    provider_name: str = Field(..., description="Environmental provider name.")
    dataset_id: str = Field(..., description="Dataset or product identifier.")
    model_source: Optional[str] = Field(None, description="Atmospheric or oceanographic numerical model name (e.g. 'GFS', 'ERA5').")
    access_provider: Optional[str] = Field(None, description="Direct API or third-party service provider (e.g. 'Open-Meteo', 'CDS API').")
    field_type: str = Field(..., description="'surface_wind' or 'ocean_currents'.")
    data_category: str = Field(..., description="'historical' or 'forecast'.")
    source_type: str = Field(..., description="Provenance source classification: 'LIVE_REMOTE', 'LOCAL_CACHE', or 'LOCAL_TEST_FIXTURE'.")
    cache_status: str = Field(default="none", description="Cache status: 'hit', 'miss', 'direct', etc.")
    requested_time_range: Optional[TimeWindowSummary] = Field(None, description="Requested temporal window [start, end].")
    actual_time_range: Optional[TimeWindowSummary] = Field(None, description="Actual coverage window available from dataset.")
    filepath: Optional[str] = Field(None, exclude=True, description="Active local NetCDF filepath (excluded from public serialization).")
    used_in_numerical_simulation: bool = Field(default=True, description="Whether this field was directly sampled in advection.")
    notes: Optional[str] = Field(None, description="Specific scientific/operational provenance notes.")


class EnvironmentOutputSummary(BaseModel):
    """Environmental domain and provenance for all four hydrodynamic/atmospheric providers."""
    domain: EnvironmentDomainSummary
    historical_window: TimeWindowSummary
    forecast_window: TimeWindowSummary
    forecast_provenance_status: str = Field(
        default="HISTORICAL_REPLAY_FIXTURE",
        description="Top-level forecast provenance status: 'LIVE_OPERATIONAL', 'HISTORICAL_REPLAY_FIXTURE', or 'MIXED'."
    )
    forecast_provenance_notes: str = Field(
        default="Historical replay forecast: forecast forcing for 2018 is supplied by local historical fixture data because current operational GFS does not archive the 2018 forecast cycle.",
        description="Explicit scientific provenance description."
    )
    fields: Dict[str, EnvironmentalFieldProvenance] = Field(
        default_factory=dict,
        description="Machine-readable provenance records for historical_wind, historical_currents, forecast_wind, forecast_currents."
    )
    providers: Dict[str, Any] = Field(
        default_factory=dict,
        description="Dataset provenance dictionaries for historical wind, historical currents, forecast wind, forecast currents."
    )


class OriginUncertaintySummary(BaseModel):
    """Spatial dispersion uncertainty bounds for estimated origin candidate region."""
    spread_radius_km: float = Field(..., ge=0.0, description="Estimated spatial dispersion radius in km.")
    semi_major_axis_km: Optional[float] = Field(None, description="Dispersion ellipse semi-major axis in km.")
    semi_minor_axis_km: Optional[float] = Field(None, description="Dispersion ellipse semi-minor axis in km.")
    orientation_deg: Optional[float] = Field(None, description="Ellipse orientation in degrees from North.")
    uncertainty_polygon: Optional[GeoJSONGeometry] = Field(None, description="Statistical dispersion ellipse polygon.")


class OriginCandidateSummary(BaseModel):
    """Single evaluated candidate origin convergence region."""
    candidate_id: str
    centroid: LatLonCoord
    evidence_score: float = Field(..., ge=0.0, le=1.0, description="Normalized model evidence score [0.0 to 1.0], NOT a calibrated probability.")
    release_time_utc: datetime
    hours_before_t0: float
    uncertainty: OriginUncertaintySummary
    active_particles: int


class OriginOutputSummary(BaseModel):
    """Estimated candidate origin region, release-time window, and trajectory convergence metrics."""
    best_candidate: Optional[OriginCandidateSummary] = None
    evidence_score: Optional[float] = Field(None, description="Normalized model evidence score (0.0 to 1.0) of best candidate; NOT a calibrated probability.")
    release_time_window: ReleaseTimeWindowRange = Field(..., description="Single source of truth for candidate release time interval.")
    candidate_count: int = Field(..., description="Number of evaluated candidate origin clusters.")
    uncertainty: Optional[OriginUncertaintySummary] = None
    candidates: List[OriginCandidateSummary] = Field(default_factory=list)
    search_horizon_hours: float = Field(72.0, description="Historical search horizon (default 72h).")
    disclaimer: str = Field(
        default="The origin score is a normalized evidence/confidence metric and is not a calibrated probability. The candidate region is an estimated convergence zone, not a confirmed spill source.",
        description="Scientific interpretation disclaimer."
    )


class ForecastHorizonSummary(BaseModel):
    """Forecast state at a specific future checkpoint horizon (+6h, +12h, +24h, +48h)."""
    horizon_hours: float = Field(..., description="Lead time in hours relative to T0.")
    timestamp: datetime = Field(..., description="Target UTC forecast timestamp.")
    centroid: LatLonCoord = Field(..., description="Predicted slick centroid at this horizon.")
    active_particles: int = Field(..., ge=0, description="Number of active Lagrangian particles.")
    total_particles: int = Field(..., ge=0, description="Total particles simulated.")
    spread_radius_km: float = Field(..., ge=0.0, description="Spatial dispersion spread radius in km.")
    uncertainty: ForecastUncertainty
    simulation_quality: str = Field(
        default="HIGH",
        description="Numerical simulation quality flag ('HIGH', 'MEDIUM', 'LOW') based on active particle retention and domain boundary containment. NOT an empirical forecast accuracy estimate."
    )
    quality: str = Field(..., description="Forecast horizon quality flag ('HIGH', 'MEDIUM', 'LOW').")
    valid: bool = Field(True, description="Whether forecast horizon has sufficient environmental coverage and active particles.")
    predicted_slick_polygon: Optional[GeoJSONGeometry] = None


class ForecastInitializationSummary(BaseModel):
    """Forecast initialization provenance."""
    source: str = Field(default="observed_feature1_slick", description="Sole initialization anchor for forward forecast.")
    time: datetime = Field(..., description="Observation timestamp T0.")
    centroid: LatLonCoord = Field(..., description="Observed slick centroid.")
    notes: str = Field(
        default="Forward forecasting is initialized strictly from the observed Feature 1 slick at T0. Backward origin reconstruction is auxiliary attribution metadata and is not used as the forecast initialization.",
        description="Scientific initialization note."
    )


class ForecastEnsembleSummary(BaseModel):
    """Technical metadata detailing the Lagrangian particle ensemble configuration."""
    ensemble_realizations: int = Field(1, ge=1, description="Number of independent stochastic simulation realizations.")
    particles_per_realization: int = Field(50, ge=1, description="Number of particles simulated inside each realization.")
    total_particles: int = Field(50, ge=1, description="Actual total number of particles numerically simulated for the run (ensemble_realizations * particles_per_realization).")
    particles_per_slick: int = Field(50, ge=1, description="Legacy alias for particles_per_realization (preserved for backward compatibility).")
    horizontal_diffusivity_m2_s: float = Field(10.0, description="Stochastic horizontal diffusivity Kh in m²/s.")
    ensemble_classification: str = Field(
        default="stochastic_particle_realization",
        description="Stochastic Lagrangian particle cloud; NOT a multi-model calibrated probabilistic ensemble."
    )
    dispersion_interpretation: str = Field(
        default="Spatial dispersion bounds represent numerical sub-grid turbulent diffusion spread, not a calibrated statistical confidence interval.",
        description="Dispersion interpretation disclaimer."
    )

    @model_validator(mode="before")
    @classmethod
    def _reconcile_particle_counts(cls, data: Any) -> Any:
        if isinstance(data, dict):
            realizations = data.get("ensemble_realizations", 1)
            p_per_real = data.get("particles_per_realization", data.get("particles_per_slick", 50))
            expected_total = realizations * p_per_real
            explicit_total = data.get("total_particles")

            if explicit_total is not None:
                if explicit_total != expected_total:
                    raise ValueError(
                        f"total_particles ({explicit_total}) must equal "
                        f"ensemble_realizations ({realizations}) * particles_per_realization ({p_per_real}) = {expected_total}."
                    )
            else:
                data["total_particles"] = expected_total

            data["ensemble_realizations"] = realizations
            data["particles_per_realization"] = p_per_real
            data["particles_per_slick"] = p_per_real
        return data

    @model_validator(mode="after")
    def _validate_total_particles_invariant(self) -> "ForecastEnsembleSummary":
        expected_total = self.ensemble_realizations * self.particles_per_realization
        if self.total_particles != expected_total:
            raise ValueError(
                f"total_particles ({self.total_particles}) must equal "
                f"ensemble_realizations ({self.ensemble_realizations}) * particles_per_realization ({self.particles_per_realization}) = {expected_total}."
            )
        return self


class ForecastOutputSummary(BaseModel):
    """Forward trajectory forecast starting strictly from observed Feature 1 slick at T0 across standard horizons."""
    initialization: ForecastInitializationSummary
    horizons: List[ForecastHorizonSummary] = Field(default_factory=list)
    ensemble: Optional[ForecastEnsembleSummary] = None


class QualityAssessmentSummary(BaseModel):
    """Deterministic quality evaluation based on provider domain coverage and particle retention."""
    overall_simulation_quality: str = Field(default="HIGH", description="Numerical simulation quality flag ('HIGH', 'MEDIUM', or 'LOW').")
    overall: str = Field(..., description="Compatibility alias for overall_simulation_quality ('HIGH', 'MEDIUM', or 'LOW').")
    quality_metric_type: str = Field(
        default="numerical_simulation_integrity",
        description="Indicates metric measures domain containment and particle retention, NOT empirical forecast accuracy."
    )
    accuracy_notice: str = Field(
        default="The 'HIGH' quality rating reflects numerical simulation integrity (active particle retention and environmental domain coverage). It is NOT an empirical forecast accuracy estimate.",
        description="Explicit scientific accuracy disclaimer."
    )
    historical_data_complete: bool
    forecast_data_complete: bool
    particle_retention_ratio: float = Field(..., ge=0.0, le=1.0)
    coverage_warnings: List[str] = Field(default_factory=list)
    assessment_rule: str = Field(
        default="Deterministic evaluation based on provider domain coverage completeness and active particle retention fraction.",
        description="Deterministic evaluation rule."
    )


class ReproducibilitySummary(BaseModel):
    """Reproducibility metadata for scientific traceability."""
    random_seed: Optional[int]
    ensemble_size: int
    particles_per_slick: int
    simulation_step_seconds: int
    configuration_hash: str = Field(..., description="Deterministic SHA256 configuration hash.")
    feature2_version: str = Field(default="1.0.0")


class UnifiedFeature2Result(BaseModel):
    """Unified, audit-ready Feature 2 end-to-end result contract."""
    feature2_version: str = Field(default="1.0.0")
    spill_id: str
    observation: ObservationOutputSummary
    environment: EnvironmentOutputSummary
    origin: OriginOutputSummary
    forecast: ForecastOutputSummary
    quality: QualityAssessmentSummary
    reproducibility: ReproducibilitySummary
    disclaimers: ScientificDisclaimers = Field(default_factory=ScientificDisclaimers)


# Rebuild Pydantic forward references
Feature2PipelineResponse.model_rebuild()

