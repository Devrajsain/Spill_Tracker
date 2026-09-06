"""
Unit tests for Pydantic input and output validation schemas.
"""

from datetime import datetime
import unittest
from feature2.schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry
from feature2.schemas.output_schema import (
    CandidateOrigin,
    OriginAnalysisResult,
    ForecastStepResult,
    ForecastAnalysisResult,
    SpatialUncertainty,
    ReleaseTimeWindow,
    ScientificDisclaimers,
    Feature2PipelineResponse,
)


class TestSchemas(unittest.TestCase):

    def setUp(self):
        self.valid_input_data = {
            "spill_id": "SAR-SPILL-001",
            "observation_time": "2026-09-02T10:00:00Z",
            "area_sq_km": 3.25,
            "perimeter_km": 8.4,
            "centroid": {"latitude": 18.92, "longitude": 72.83},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [[72.82, 18.91], [72.84, 18.91], [72.84, 18.93], [72.82, 18.93], [72.82, 18.91]]
                ]
            }
        }

    def test_valid_input_parsing(self):
        slick = SlickDetectionInput(**self.valid_input_data)
        self.assertEqual(slick.spill_id, "SAR-SPILL-001")
        self.assertEqual(slick.centroid.latitude, 18.92)
        self.assertEqual(slick.area_sq_km, 3.25)

    def test_invalid_coordinates_raise_error(self):
        invalid_data = self.valid_input_data.copy()
        invalid_data["centroid"] = {"latitude": 150.0, "longitude": 72.83}  # Latitude out of range
        with self.assertRaises(Exception):
            SlickDetectionInput(**invalid_data)

    def test_output_schema_serialization_and_disclaimers(self):
        disclaimer = ScientificDisclaimers()
        self.assertIn("Lagrangian", disclaimer.methodology)
        self.assertIn("relative evidence", disclaimer.confidence_score_definition.lower())

        origin_res = OriginAnalysisResult(
            spill_id="SAR-SPILL-001",
            observation_time=datetime.fromisoformat("2026-09-02T10:00:00"),
            search_horizon_hours=72.0,
            candidate_origins=[],
            disclaimers=disclaimer
        )
        self.assertEqual(len(origin_res.candidate_origins), 0)
        self.assertEqual(origin_res.search_horizon_hours, 72.0)


if __name__ == "__main__":
    unittest.main()
