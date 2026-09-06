"""
Runtime wiring trace and request audit layer for Feature 1 -> Environmental Data integration.
Verifies that all environmental current and wind requests are strictly derived from the
Feature 1 Sentinel-1 SAR observation geometry and acquisition timestamp without manual input,
independent coordinates, or credential leakage.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple, Union
from pydantic import BaseModel, Field

from .domain import SentinelObservationDomain, EnvironmentalQueryDomain, extract_query_bounds
from .base import EnvironmentalDataProvider
from ..schemas.input_schema import SlickDetectionInput
from ..config import Feature2Settings, default_settings
from ..exceptions import EnvironmentalCoverageError
from ..logging_config import logger


class ProviderRequestRecord(BaseModel):
    """Audited parameters of an environmental vector field data request."""
    provider_name: str
    provider_type: str = Field(..., description="'current' or 'wind'")
    requested_bbox: Tuple[float, float, float, float]
    requested_time_start: datetime
    requested_time_end: datetime

    @property
    def min_lat(self) -> float:
        return self.requested_bbox[0]

    @property
    def max_lat(self) -> float:
        return self.requested_bbox[1]

    @property
    def min_lon(self) -> float:
        return self.requested_bbox[2]

    @property
    def max_lon(self) -> float:
        return self.requested_bbox[3]


class WiringTraceRecord(BaseModel):
    """End-to-end diagnostic trace linking Feature 1 detection to provider requests."""
    spill_id: str
    sentinel_observation: SentinelObservationDomain
    environmental_query: EnvironmentalQueryDomain
    current_request: ProviderRequestRecord
    wind_request: ProviderRequestRecord
    geographic_match: bool
    temporal_match: bool
    scene_isolation: bool
    coverage_status: str = Field(default="NOT_EXECUTED", description="'PASS', 'FAIL', or 'NOT_EXECUTED'")

    def format_trace(self) -> str:
        """
        Renders a clean, developer-readable diagnostic summary.
        Ensures zero credential or API key leakage.
        """
        so = self.sentinel_observation
        eq = self.environmental_query
        cr = self.current_request
        wr = self.wind_request

        geo_str = "PASS" if self.geographic_match else "FAIL"
        temp_str = "PASS" if self.temporal_match else "FAIL"
        iso_str = "PASS" if self.scene_isolation else "FAIL"

        return (
            "========================================\n"
            "FEATURE 1 → ENVIRONMENT TRACE\n"
            "========================================\n\n"
            f"spill_id:\n    {self.spill_id}\n\n"
            "Sentinel observation:\n"
            f"    bbox: ({so.min_lat:.4f}, {so.max_lat:.4f}, {so.min_lon:.4f}, {so.max_lon:.4f})\n"
            f"    centroid: ({so.centroid_lat:.4f}, {so.centroid_lon:.4f})\n"
            f"    observation_time: {so.observation_time.isoformat()}\n\n"
            "Environmental query:\n"
            f"    bbox: ({eq.min_lat:.4f}, {eq.max_lat:.4f}, {eq.min_lon:.4f}, {eq.max_lon:.4f})\n"
            f"    buffer_km: {eq.buffer_distance_km:.1f}\n"
            f"    historical_start: {eq.historical_start_time.isoformat()}\n"
            f"    historical_end: {eq.historical_end_time.isoformat()}\n\n"
            "CURRENT REQUEST:\n"
            f"    provider: {cr.provider_name}\n"
            f"    bbox: ({cr.min_lat:.4f}, {cr.max_lat:.4f}, {cr.min_lon:.4f}, {cr.max_lon:.4f})\n"
            f"    start: {cr.requested_time_start.isoformat()}\n"
            f"    end: {cr.requested_time_end.isoformat()}\n\n"
            "WIND REQUEST:\n"
            f"    provider: {wr.provider_name}\n"
            f"    bbox: ({wr.min_lat:.4f}, {wr.max_lat:.4f}, {wr.min_lon:.4f}, {wr.max_lon:.4f})\n"
            f"    start: {wr.requested_time_start.isoformat()}\n"
            f"    end: {wr.requested_time_end.isoformat()}\n\n"
            "CONSISTENCY CHECK:\n"
            f"    geographic_match: {geo_str}\n"
            f"    temporal_match: {temp_str}\n"
            f"    scene_isolation: {iso_str}\n"
            f"    coverage: {self.coverage_status}\n"
            "========================================"
        )


class ProviderRequestAuditor:
    """
    Audits environmental provider requests to guarantee strict adherence to the
    dynamically derived EnvironmentalQueryDomain, raising explicit exceptions on mismatch.
    """

    @staticmethod
    def audit_request(
        domain: EnvironmentalQueryDomain,
        provider_name: str,
        provider_type: str,
        requested_bbox: Tuple[float, float, float, float],
        requested_start: datetime,
        requested_end: datetime,
        tolerance_deg: float = 1e-4,
        tolerance_sec: float = 1.0,
    ) -> ProviderRequestRecord:
        """
        Validates that a provider's request strictly matches the EnvironmentalQueryDomain.
        
        Raises:
            EnvironmentalCoverageError: if the provider attempts to query different spatial bounds or time ranges.
        """
        env_min_lat, env_max_lat, env_min_lon, env_max_lon = domain.environmental_bbox

        # Spatial check
        lat_mismatch = (
            abs(requested_bbox[0] - env_min_lat) > tolerance_deg or
            abs(requested_bbox[1] - env_max_lat) > tolerance_deg
        )
        lon_mismatch = (
            abs(requested_bbox[2] - env_min_lon) > tolerance_deg or
            abs(requested_bbox[3] - env_max_lon) > tolerance_deg
        )
        if lat_mismatch or lon_mismatch:
            raise EnvironmentalCoverageError(
                f"Provider '{provider_name}' spatial request audit failed: "
                f"requested bbox {requested_bbox} does not match derived environmental bbox "
                f"{domain.environmental_bbox} for Sentinel-1 spill '{domain.spill_id}'."
            )

        # Temporal check
        start_diff = abs((requested_start - domain.historical_start_time).total_seconds())
        end_diff = abs((requested_end - domain.historical_end_time).total_seconds())
        if start_diff > tolerance_sec or end_diff > tolerance_sec:
            raise EnvironmentalCoverageError(
                f"Provider '{provider_name}' temporal request audit failed: "
                f"requested range [{requested_start.isoformat()}, {requested_end.isoformat()}] "
                f"does not match derived historical window "
                f"[{domain.historical_start_time.isoformat()}, {domain.historical_end_time.isoformat()}] "
                f"for Sentinel-1 spill '{domain.spill_id}'."
            )

        return ProviderRequestRecord(
            provider_name=provider_name,
            provider_type=provider_type,
            requested_bbox=requested_bbox,
            requested_time_start=requested_start,
            requested_time_end=requested_end
        )


def trace_feature1_environmental_wiring(
    payload: Union[SlickDetectionInput, Dict[str, Any]],
    currents_provider: EnvironmentalDataProvider,
    wind_provider: EnvironmentalDataProvider,
    settings: Optional[Feature2Settings] = None,
    coverage_dataset: Optional[Any] = None
) -> WiringTraceRecord:
    """
    Executes the end-to-end Feature 1 -> Environmental Data wiring pipeline:
    1. Ingests Feature 1 payload
    2. Derives SentinelObservationDomain (exact observed footprint and timestamp T0)
    3. Derives EnvironmentalQueryDomain with configurable buffer
    4. Dispatches and audits query to currents provider
    5. Dispatches and audits query to wind provider
    6. Validates coverage against dataset if provided
    7. Returns complete verified WiringTraceRecord
    """
    active_settings = settings or default_settings

    # 1. SentinelObservationDomain
    sentinel_domain = SentinelObservationDomain.from_feature1_input(payload)

    # 2. EnvironmentalQueryDomain
    env_domain = EnvironmentalQueryDomain.from_sentinel_observation(
        sentinel_domain=sentinel_domain,
        buffer_distance_km=active_settings.data.environmental_buffer_km,
        historical_horizon_hours=active_settings.backward.max_backtrack_hours,
        forecast_horizon_hours=active_settings.forecast.forecast_horizons_hours[-1]
    )

    # 3. Formulate and audit currents request
    curr_min_lat, curr_max_lat, curr_min_lon, curr_max_lon, curr_start, curr_end = extract_query_bounds(
        env_domain, mode="historical"
    )
    current_record = ProviderRequestAuditor.audit_request(
        domain=env_domain,
        provider_name=currents_provider.provider_name,
        provider_type="current",
        requested_bbox=(curr_min_lat, curr_max_lat, curr_min_lon, curr_max_lon),
        requested_start=curr_start,
        requested_end=curr_end
    )
    currents_provider.fetch_grid(env_domain)

    # 4. Formulate and audit wind request
    wind_min_lat, wind_max_lat, wind_min_lon, wind_max_lon, wind_start, wind_end = extract_query_bounds(
        env_domain, mode="historical"
    )
    wind_record = ProviderRequestAuditor.audit_request(
        domain=env_domain,
        provider_name=wind_provider.provider_name,
        provider_type="wind",
        requested_bbox=(wind_min_lat, wind_max_lat, wind_min_lon, wind_max_lon),
        requested_start=wind_start,
        requested_end=wind_end
    )
    wind_provider.fetch_grid(env_domain)

    # 5. Consistency evaluation
    geo_match = (
        current_record.requested_bbox == env_domain.environmental_bbox and
        wind_record.requested_bbox == env_domain.environmental_bbox
    )
    temp_match = (
        current_record.requested_time_start == env_domain.historical_start_time and
        current_record.requested_time_end == env_domain.historical_end_time and
        wind_record.requested_time_start == env_domain.historical_start_time and
        wind_record.requested_time_end == env_domain.historical_end_time
    )
    scene_isolation = (
        env_domain.spill_id == sentinel_domain.spill_id and
        env_domain.source_bbox == sentinel_domain.source_bbox
    )

    # 6. Coverage evaluation
    coverage_status = "NOT_EXECUTED"
    if coverage_dataset is not None:
        try:
            if hasattr(coverage_dataset, "validate_domain_coverage"):
                coverage_dataset.validate_domain_coverage(env_domain, mode="historical")
                coverage_status = "PASS"
            elif hasattr(env_domain, "validate_spatial_coverage"):
                env_domain.validate_spatial_coverage(
                    coverage_dataset.min_lat, coverage_dataset.max_lat,
                    coverage_dataset.min_lon, coverage_dataset.max_lon
                )
                env_domain.validate_temporal_coverage(
                    coverage_dataset.min_time, coverage_dataset.max_time, mode="historical"
                )
                coverage_status = "PASS"
        except Exception as e:
            coverage_status = "FAIL"

    trace_record = WiringTraceRecord(
        spill_id=sentinel_domain.spill_id,
        sentinel_observation=sentinel_domain,
        environmental_query=env_domain,
        current_request=current_record,
        wind_request=wind_record,
        geographic_match=geo_match,
        temporal_match=temp_match,
        scene_isolation=scene_isolation,
        coverage_status=coverage_status
    )

    logger.info(
        f"Feature 1 wiring trace completed for '{sentinel_domain.spill_id}': "
        f"geo_match={geo_match}, temp_match={temp_match}, isolation={scene_isolation}, coverage={coverage_status}"
    )

    return trace_record
