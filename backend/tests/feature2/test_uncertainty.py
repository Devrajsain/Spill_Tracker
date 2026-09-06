"""
Unit tests for spatial covariance ellipse calculation and temporal uncertainty bounds.
"""

from datetime import datetime, timedelta
import unittest
import numpy as np
from feature2.uncertainty.spatial_error import SpatialUncertaintyEstimator
from feature2.uncertainty.temporal_error import TemporalUncertaintyEstimator


class TestUncertainty(unittest.TestCase):

    def test_dynamic_spatial_covariance_ellipse(self):
        # Generate synthetic cluster of particles around (18.5, 72.5) with known spread
        np.random.seed(42)
        lats = np.random.normal(18.5, 0.02, 100)
        lons = np.random.normal(72.5, 0.05, 100)
        coords = list(zip(lats, lons))

        uncert = SpatialUncertaintyEstimator.compute_dispersion_ellipse(coords)

        self.assertGreater(uncert.semi_major_axis_km, 0.0)
        self.assertGreater(uncert.semi_minor_axis_km, 0.0)
        self.assertGreaterEqual(uncert.semi_major_axis_km, uncert.semi_minor_axis_km)
        self.assertEqual(uncert.uncertainty_polygon.type, "Polygon")
        self.assertGreater(len(uncert.uncertainty_polygon.coordinates[0]), 10)

    def test_temporal_uncertainty_bounds(self):
        peak = datetime.fromisoformat("2026-09-02T12:00:00")
        window = TemporalUncertaintyEstimator.calculate_bounds(peak, window_hours=12.0)

        self.assertEqual(window.earliest_utc, peak - timedelta(hours=6))
        self.assertEqual(window.latest_utc, peak + timedelta(hours=6))
        self.assertEqual(window.window_duration_hours, 12.0)


if __name__ == "__main__":
    unittest.main()
