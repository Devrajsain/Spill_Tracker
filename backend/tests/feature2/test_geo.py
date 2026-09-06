"""
Unit tests for geographic coordinate conversions and spatial algorithms.
"""

import unittest
from feature2.geo.coordinates import (
    haversine_distance_km,
    meters_to_lat_deg,
    meters_to_lon_deg,
    lat_lon_to_meters,
    compute_bounding_box
)
from feature2.geo.spatial import (
    is_point_in_polygon,
    compute_polygon_centroid,
    sample_particles_in_polygon
)


class TestGeoUtilities(unittest.TestCase):

    def test_haversine_distance(self):
        # Distance between Mumbai (18.9219, 72.8347) and Goa (15.2993, 74.1240) ~425 km
        dist = haversine_distance_km(18.9219, 72.8347, 15.2993, 74.1240)
        self.assertAlmostEqual(dist, 425.0, delta=20.0)

    def test_meters_to_degrees_consistency(self):
        d_lat_deg = meters_to_lat_deg(111320.0)
        self.assertAlmostEqual(d_lat_deg, 1.0, delta=0.01)

        d_lon_deg = meters_to_lon_deg(111320.0, at_latitude=0.0)
        self.assertAlmostEqual(d_lon_deg, 1.0, delta=0.01)

    def test_point_in_polygon(self):
        box_polygon = [
            [72.0, 18.0],
            [73.0, 18.0],
            [73.0, 19.0],
            [72.0, 19.0],
            [72.0, 18.0]
        ]
        # Inside
        self.assertTrue(is_point_in_polygon(72.5, 18.5, box_polygon))
        # Outside
        self.assertFalse(is_point_in_polygon(71.5, 18.5, box_polygon))
        self.assertFalse(is_point_in_polygon(72.5, 19.5, box_polygon))

    def test_sample_particles_in_polygon(self):
        box_polygon = [
            [72.0, 18.0],
            [73.0, 18.0],
            [73.0, 19.0],
            [72.0, 19.0],
            [72.0, 18.0]
        ]
        particles = sample_particles_in_polygon(box_polygon, num_particles=50, random_seed=42)
        self.assertEqual(len(particles), 50)
        for lat, lon in particles:
            self.assertTrue(is_point_in_polygon(lon, lat, box_polygon))


if __name__ == "__main__":
    unittest.main()
