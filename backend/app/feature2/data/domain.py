"""
Geographic and temporal domain models anchoring Feature 2 to Sentinel-1 SAR observations.
Eliminates hardcoded geographic regions by dynamically calculating spatial bounding boxes
with configurable simulation transport buffers and historical/forecast time horizons.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, field_validator

from ..geo.coordinates import compute_bounding_box
from ..schemas.input_schema import SlickDetectionInput, GeoJSONGeometry, CentroidCoordinates
from ..data.time_utils import normalize_to_utc
from ..exceptions import EnvironmentalCoverageError, InvalidInputGeometryError


class SentinelObservationDomain(BaseModel):
    """
    Geographic footprint and temporal anchor of a Sentinel-1 SAR observation.
    Extracted dynamically from Feature 1 slick detection payloads across any global scene.
    """
    spill_id: str = Field(..., description="Spill identifier from Sentinel-1 detection.")
    observation_time: datetime = Field(..., description="UTC timestamp T0 of Sentinel-1 acquisition.")
    centroid_lat: float = Field(..., ge=-90.0, le=90.0, description="Centroid latitude in decimal degrees.")
    centroid_lon: float = Field(..., ge=-180.0, le=180.0, description="Centroid longitude in decimal degrees.")
    min_lat: float = Field(..., ge=-90.0, le=90.0, description="Minimum latitude of observed slick polygon.")
    max_lat: float = Field(..., ge=-90.0, le=90.0, description="Maximum latitude of observed slick polygon.")
    min_lon: float = Field(..., description="Minimum longitude of observed slick polygon.")
    max_lon: float = Field(..., description="Maximum longitude of observed slick polygon.")
    area_sq_km: Optional[float] = Field(None, description="Observed slick area in sq km.")
    perimeter_km: Optional[float] = Field(None, description="Observed slick perimeter in km.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Sentinel-1 scene metadata (sensor, pass, polarization).")

    @property
    def source_bbox(self) -> Tuple[float, float, float, float]:
        """Returns (min_lat, max_lat, min_lon, max_lon) of observed slick."""
        return self.min_lat, self.max_lat, self.min_lon, self.max_lon

    @classmethod
    def from_feature1_input(
        cls,
        payload: Union[SlickDetectionInput, Dict[str, Any]]
    ) -> "SentinelObservationDomain":
        """
        Constructs a SentinelObservationDomain directly from a Feature 1 detection payload.
        Handles GeoJSON Polygon or MultiPolygon geometries without manual coordinate entry.
        """
        if isinstance(payload, dict):
            slick = SlickDetectionInput(**payload)
        elif isinstance(payload, SlickDetectionInput):
            slick = payload
        else:
            raise InvalidInputGeometryError(f"Unsupported payload type: {type(payload)}")

        coords = slick.geometry.coordinates
        # Extract all (lat, lon) vertices
        all_pts: List[Tuple[float, float]] = []
        if slick.geometry.type == "Polygon":
            for ring in coords:
                for pt in ring:
                    # GeoJSON is [lon, lat]
                    all_pts.append((float(pt[1]), float(pt[0])))
        elif slick.geometry.type == "MultiPolygon":
            for poly in coords:
                for ring in poly:
                    for pt in ring:
                        all_pts.append((float(pt[1]), float(pt[0])))
        else:
            raise InvalidInputGeometryError(f"Unsupported geometry type: {slick.geometry.type}")

        if not all_pts:
            # Fallback to centroid if coordinates array was empty
            all_pts = [(slick.centroid.latitude, slick.centroid.longitude)]

        min_lat, max_lat, min_lon, max_lon = compute_bounding_box(all_pts, buffer_km=0.0)

        return cls(
            spill_id=slick.spill_id,
            observation_time=normalize_to_utc(slick.observation_time),
            centroid_lat=slick.centroid.latitude,
            centroid_lon=slick.centroid.longitude,
            min_lat=min_lat,
            max_lat=max_lat,
            min_lon=min_lon,
            max_lon=max_lon,
            area_sq_km=slick.area_sq_km,
            perimeter_km=slick.perimeter_km,
            metadata=slick.metadata
        )

    from_slick_input = from_feature1_input


class EnvironmentalQueryDomain(BaseModel):
    """
    Environmental data query domain dynamically derived from a Sentinel-1 observation.
    Includes spatial transport buffer padding and historical/forecast search windows.
    """
    spill_id: str
    observation_time: datetime
    source_bbox: Tuple[float, float, float, float] = Field(
        ..., description="Raw Sentinel-1 slick bounding box (min_lat, max_lat, min_lon, max_lon)."
    )
    environmental_bbox: Tuple[float, float, float, float] = Field(
        ..., description="Buffered bounding box (min_lat, max_lat, min_lon, max_lon) for environmental data."
    )
    buffer_distance_km: float = Field(..., ge=0.0, description="Applied spatial buffer padding in kilometers.")
    historical_start_time: datetime = Field(..., description="Earliest historical timestamp for backtracking (T0 - horizon).")
    historical_end_time: datetime = Field(..., description="Observation timestamp T0.")
    forecast_start_time: datetime = Field(..., description="Observation timestamp T0.")
    forecast_end_time: datetime = Field(..., description="Maximum forecast timestamp (T0 + forecast_horizon).")
    historical_horizon_hours: float = Field(..., gt=0.0, description="Historical backtracking search window duration in hours.")
    forecast_horizon_hours: float = Field(..., ge=0.0, description="Forward forecast duration in hours.")

    @property
    def min_lat(self) -> float:
        return self.environmental_bbox[0]

    @property
    def max_lat(self) -> float:
        return self.environmental_bbox[1]

    @property
    def min_lon(self) -> float:
        return self.environmental_bbox[2]

    @property
    def max_lon(self) -> float:
        return self.environmental_bbox[3]

    @classmethod
    def from_sentinel_observation(
        cls,
        sentinel_domain: SentinelObservationDomain,
        buffer_distance_km: float = 50.0,
        historical_horizon_hours: float = 72.0,
        forecast_horizon_hours: float = 48.0,
    ) -> "EnvironmentalQueryDomain":
        """
        Derives an EnvironmentalQueryDomain by buffering the Sentinel-1 footprint
        and calculating historical/forecast spacetime windows from observation_time T0.
        """
        source_pts = [
            (sentinel_domain.min_lat, sentinel_domain.min_lon),
            (sentinel_domain.max_lat, sentinel_domain.max_lon),
        ]
        # Apply geodetic buffer padding in km
        buf_min_lat, buf_max_lat, buf_min_lon, buf_max_lon = compute_bounding_box(
            source_pts,
            buffer_km=buffer_distance_km
        )

        obs_time = normalize_to_utc(sentinel_domain.observation_time)
        hist_start = obs_time - timedelta(hours=historical_horizon_hours)
        hist_end = obs_time
        fc_start = obs_time
        fc_end = obs_time + timedelta(hours=forecast_horizon_hours)

        return cls(
            spill_id=sentinel_domain.spill_id,
            observation_time=obs_time,
            source_bbox=sentinel_domain.source_bbox,
            environmental_bbox=(buf_min_lat, buf_max_lat, buf_min_lon, buf_max_lon),
            buffer_distance_km=buffer_distance_km,
            historical_start_time=hist_start,
            historical_end_time=hist_end,
            forecast_start_time=fc_start,
            forecast_end_time=fc_end,
            historical_horizon_hours=historical_horizon_hours,
            forecast_horizon_hours=forecast_horizon_hours,
        )

    def validate_spatial_coverage(
        self,
        dataset_min_lat: float,
        dataset_max_lat: float,
        dataset_min_lon: float,
        dataset_max_lon: float,
        strict_buffer: bool = False
    ) -> None:
        """
        Validates whether the dataset covers the Sentinel-1 scene domain (or buffered domain).
        Raises EnvironmentalCoverageError if not covered.
        """
        check_min_lat, check_max_lat, check_min_lon, check_max_lon = (
            self.environmental_bbox if strict_buffer else self.source_bbox
        )

        tol = 1e-5
        if (check_min_lat < dataset_min_lat - tol or
            check_max_lat > dataset_max_lat + tol or
            check_min_lon < dataset_min_lon - tol or
            check_max_lon > dataset_max_lon + tol):
            raise EnvironmentalCoverageError(
                f"Environmental dataset spatial domain lat[{dataset_min_lat:.2f}, {dataset_max_lat:.2f}], "
                f"lon[{dataset_min_lon:.2f}, {dataset_max_lon:.2f}] does not cover required Sentinel-1 domain "
                f"lat[{check_min_lat:.2f}, {check_max_lat:.2f}], lon[{check_min_lon:.2f}, {check_max_lon:.2f}] "
                f"for spill '{self.spill_id}'."
            )

    def validate_temporal_coverage(
        self,
        dataset_min_time: datetime,
        dataset_max_time: datetime,
        mode: str = "historical"
    ) -> None:
        """
        Validates whether the dataset covers the required historical or forecast time range.
        Raises EnvironmentalCoverageError if not covered.
        """
        req_start = self.historical_start_time if mode == "historical" else self.forecast_start_time
        req_end = self.historical_end_time if mode == "historical" else self.forecast_end_time

        ds_min_utc = normalize_to_utc(dataset_min_time)
        ds_max_utc = normalize_to_utc(dataset_max_time)
        tol_sec = 60.0

        if (req_start.timestamp() < ds_min_utc.timestamp() - tol_sec or
            req_end.timestamp() > ds_max_utc.timestamp() + tol_sec):
            raise EnvironmentalCoverageError(
                f"Environmental dataset temporal coverage [{ds_min_utc.isoformat()}, {ds_max_utc.isoformat()}] "
                f"does not cover required {mode} window [{req_start.isoformat()}, {req_end.isoformat()}] "
                f"for spill '{self.spill_id}'."
            )


def extract_query_bounds(
    query_obj: Any,
    mode: str = "historical"
) -> Tuple[float, float, float, float, datetime, datetime]:
    """
    Extracts (min_lat, max_lat, min_lon, max_lon, start_time, end_time) from
    either an EnvironmentalQueryDomain or EnvironmentalQueryWindow.
    """
    if isinstance(query_obj, EnvironmentalQueryDomain):
        min_lat, max_lat, min_lon, max_lon = query_obj.environmental_bbox
        start_time = query_obj.historical_start_time if mode == "historical" else query_obj.forecast_start_time
        end_time = query_obj.historical_end_time if mode == "historical" else query_obj.forecast_end_time
        return min_lat, max_lat, min_lon, max_lon, start_time, end_time

    if hasattr(query_obj, "min_lat") and hasattr(query_obj, "start_time"):
        return (
            float(query_obj.min_lat),
            float(query_obj.max_lat),
            float(query_obj.min_lon),
            float(query_obj.max_lon),
            normalize_to_utc(query_obj.start_time),
            normalize_to_utc(query_obj.end_time),
        )

    raise ValueError(f"Unsupported environmental query object type: {type(query_obj)}")

