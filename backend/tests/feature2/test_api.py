"""
Integration tests for FastAPI endpoints using TestClient.
"""

import unittest
from fastapi.testclient import TestClient
from main import app


class TestAPIEndpoints(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.sample_payload = {
            "spill_id": "SAR-SPILL-TEST-001",
            "observation_time": "2026-09-02T12:00:00Z",
            "area_sq_km": 4.5,
            "perimeter_km": 11.2,
            "centroid": {"latitude": 18.9219, "longitude": 72.8347},
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [72.82, 18.91],
                        [72.85, 18.91],
                        [72.85, 18.93],
                        [72.82, 18.93],
                        [72.82, 18.91]
                    ]
                ]
            }
        }

    def test_root_endpoint(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(response.json()["status"].lower(), ["online", "operational"])

    def test_health_check(self):
        response = self.client.get("/feature2/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    def test_trace_origin_endpoint(self):
        response = self.client.post("/feature2/trace-origin", json=self.sample_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["spill_id"], "SAR-SPILL-TEST-001")
        self.assertIn("disclaimers", data)

    def test_forecast_endpoint(self):
        response = self.client.post("/feature2/forecast", json=self.sample_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["spill_id"], "SAR-SPILL-TEST-001")
        self.assertEqual(len(data["horizons"]), 4)  # +6h, +12h, +24h, +48h

    def test_pipeline_endpoint(self):
        response = self.client.post("/feature2/pipeline", json=self.sample_payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["spill_id"], "SAR-SPILL-TEST-001")
        self.assertIn("origin_analysis", data)
        self.assertIn("forecast_analysis", data)


if __name__ == "__main__":
    unittest.main()
