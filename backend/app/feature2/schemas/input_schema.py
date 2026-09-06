"""
Input data models representing SAR slick detections emitted by Feature 1.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Union
from pydantic import BaseModel, Field, field_validator


class CentroidCoordinates(BaseModel):
    """Geographical centroid coordinates in WGS84."""
    latitude: float = Field(
        ...,
        ge=-90.0,
        le=90.0,
        description="Latitude of slick centroid in decimal degrees (-90 to 90)."
    )
    longitude: float = Field(
        ...,
        ge=-180.0,
        le=180.0,
        description="Longitude of slick centroid in decimal degrees (-180 to 180)."
    )


class GeoJSONGeometry(BaseModel):
    """GeoJSON Polygon or MultiPolygon geometry representation."""
    type: Literal["Polygon", "MultiPolygon"] = Field(
        ...,
        description="GeoJSON geometry type."
    )
    coordinates: List[Any] = Field(
        ...,
        description="GeoJSON coordinates array formatted according to RFC 7946."
    )

    @field_validator("coordinates")
    @classmethod
    def validate_coordinates_non_empty(cls, v: List[Any]) -> List[Any]:
        if not v:
            raise ValueError("Coordinates list cannot be empty.")
        return v


class SlickDetectionInput(BaseModel):
    """
    Standardized payload received from Feature 1 (SAR Oil Slick Detection).
    """
    spill_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the detected spill instance."
    )
    observation_time: datetime = Field(
        ...,
        description="UTC observation timestamp T0 of the SAR satellite acquisition."
    )
    area_sq_km: float = Field(
        ...,
        gt=0.0,
        description="Estimated slick surface area in square kilometers."
    )
    perimeter_km: float = Field(
        ...,
        gt=0.0,
        description="Estimated slick perimeter length in kilometers."
    )
    centroid: CentroidCoordinates = Field(
        ...,
        description="WGS84 centroid location of the observed slick."
    )
    geometry: GeoJSONGeometry = Field(
        ...,
        description="GeoJSON Polygon/MultiPolygon defining the slick boundary."
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Optional auxiliary metadata (sensor name, confidence, wind speed at capture)."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "spill_id": "SAR-SPILL-20260902-001",
                "observation_time": "2026-09-02T12:00:00Z",
                "area_sq_km": 4.52,
                "perimeter_km": 12.8,
                "centroid": {
                    "latitude": 18.9219,
                    "longitude": 72.8347
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [72.8200, 18.9100],
                            [72.8500, 18.9100],
                            [72.8500, 18.9350],
                            [72.8200, 18.9350],
                            [72.8200, 18.9100]
                        ]
                    ]
                },
                "metadata": {
                    "satellite": "Sentinel-1A",
                    "polarization": "VV"
                }
            }
        }
