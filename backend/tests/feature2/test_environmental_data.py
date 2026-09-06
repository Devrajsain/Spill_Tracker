"""
Comprehensive unit and integration tests for the Environmental Data Layer.
Tests NetCDF ingestion, spatial bilinear interpolation, temporal linear interpolation,
coordinate conversions, time normalization, domain validations, and mock providers.
"""

from datetime import datetime, timedelta, timezone
import os
import shutil
import tempfile
import unittest
import numpy as np
import pandas as pd
import xarray as xr

from feature2.data.base import (
    CurrentSample,
    WindSample,
    VectorFieldSample,
    HistoricalCurrentProvider,
    HistoricalWindProvider,
    ForecastCurrentProvider,
    ForecastWindProvider,
)
from feature2.data.coord_utils import (
    detect_longitude_convention,
    find_grid_bounding_indices,
    normalize_longitude,
)
from feature2.data.currents.local import LocalCurrentsProvider
from feature2.data.currents.mock import MockCurrentsProvider
from feature2.data.currents.copernicus import CopernicusCurrentsProvider
from feature2.data.currents.hycom import HYCOMCurrentsProvider
from feature2.data.local_netcdf import LocalNetCDFDatasetReader, VariableMapping
from feature2.data.time_utils import datetime_to_seconds, normalize_to_utc, seconds_to_datetime
from feature2.data.wind.local import LocalWindProvider
from feature2.data.wind.mock import MockWindProvider
from feature2.data.wind.era5 import ERA5WindProvider
from feature2.data.wind.gfs import GFSWindProvider
from feature2.exceptions import (
    EnvironmentalDataUnavailableError,
    InvalidDatasetError,
    OutOfDomainError,
    TemporalCoverageError,
)


class TestTimeAndCoordinateUtils(unittest.TestCase):
    """Tests for UTC time normalization and coordinate handling."""

    def test_utc_normalization_iso_strings(self):
        # With Z
        dt_z = normalize_to_utc("2026-08-27T06:30:00Z")
        self.assertEqual(dt_z.tzinfo, timezone.utc)
        self.assertEqual(dt_z.year, 2026)
        self.assertEqual(dt_z.hour, 6)

        # With +05:30 offset
        dt_offset = normalize_to_utc("2026-08-27T12:00:00+05:30")
        self.assertEqual(dt_offset.tzinfo, timezone.utc)
        self.assertEqual(dt_offset.hour, 6)
        self.assertEqual(dt_offset.minute, 30)

        # Naive datetime
        naive_dt = datetime(2026, 9, 2, 10, 0, 0)
        dt_from_naive = normalize_to_utc(naive_dt)
        self.assertEqual(dt_from_naive.tzinfo, timezone.utc)
        self.assertEqual(dt_from_naive.hour, 10)

    def test_longitude_normalization(self):
        # Target [-180, 180]
        self.assertEqual(normalize_longitude(0.0, "[-180, 180]"), 0.0)
        self.assertEqual(normalize_longitude(72.83, "[-180, 180]"), 72.83)
        self.assertEqual(normalize_longitude(180.0, "[-180, 180]"), 180.0)
        self.assertEqual(normalize_longitude(-180.0, "[-180, 180]"), -180.0)
        self.assertAlmostEqual(normalize_longitude(359.0, "[-180, 180]"), -1.0)
        self.assertAlmostEqual(normalize_longitude(190.0, "[-180, 180]"), -170.0)

        # Target [0, 360]
        self.assertEqual(normalize_longitude(0.0, "[0, 360]"), 0.0)
        self.assertEqual(normalize_longitude(72.83, "[0, 360]"), 72.83)
        self.assertAlmostEqual(normalize_longitude(-10.0, "[0, 360]"), 350.0)
        self.assertAlmostEqual(normalize_longitude(-180.0, "[0, 360]"), 180.0)

    def test_grid_bounding_indices_ascending_and_descending(self):
        # Ascending latitudes [-20, -10, 0, 10, 20]
        asc_lats = np.array([-20.0, -10.0, 0.0, 10.0, 20.0])
        i0, i1, t = find_grid_bounding_indices(asc_lats, 5.0)
        self.assertEqual(i0, 2)
        self.assertEqual(i1, 3)
        self.assertAlmostEqual(t, 0.5)

        # Descending latitudes [20, 10, 0, -10, -20]
        desc_lats = np.array([20.0, 10.0, 0.0, -10.0, -20.0])
        i0, i1, t = find_grid_bounding_indices(desc_lats, 5.0)
        self.assertIn(i0, [1, 2])
        self.assertIn(i1, [1, 2])
        # Value check: (1-t)*grid[i0] + t*grid[i1] == 5.0
        val = (1.0 - t) * desc_lats[i0] + t * desc_lats[i1]
        self.assertAlmostEqual(val, 5.0)


class TestNetCDFIngestionAndInterpolation(unittest.TestCase):
    """Unit tests using synthetic NetCDF fixtures."""

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

        # Create standard synthetic ocean currents NetCDF file:
        # Lat: 10.0 to 20.0 (step 2.0), Lon: 70.0 to 80.0 (step 2.0)
        # Times: 2026-09-01T00:00:00, 2026-09-01T06:00:00, 2026-09-01T12:00:00 (3 time steps)
        # u(t, lat, lon) = 0.1 * lat + 0.01 * lon + 0.05 * t_idx
        # v(t, lat, lon) = 0.05 * lat - 0.02 * lon - 0.03 * t_idx
        self.lats = np.arange(10.0, 22.0, 2.0)  # 6 points: 10, 12, 14, 16, 18, 20
        self.lons = np.arange(70.0, 82.0, 2.0)  # 6 points: 70, 72, 74, 76, 78, 80
        self.times = pd.date_range("2026-09-01 00:00:00", periods=3, freq="6h")

        nt, nlat, nlon = len(self.times), len(self.lats), len(self.lons)
        u_data = np.zeros((nt, nlat, nlon))
        v_data = np.zeros((nt, nlat, nlon))

        for t in range(nt):
            for i, lat in enumerate(self.lats):
                for j, lon in enumerate(self.lons):
                    u_data[t, i, j] = 0.1 * lat + 0.01 * lon + 0.05 * t
                    v_data[t, i, j] = 0.05 * lat - 0.02 * lon - 0.03 * t

        self.ds_standard = xr.Dataset(
            data_vars={
                "eastward_current": (["time", "latitude", "longitude"], u_data),
                "northward_current": (["time", "latitude", "longitude"], v_data),
            },
            coords={
                "time": self.times,
                "latitude": self.lats,
                "longitude": self.lons,
            }
        )
        self.nc_standard_path = os.path.join(self.test_dir, "test_currents.nc")
        self.ds_standard.to_netcdf(self.nc_standard_path)

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_valid_dataset_loading_and_attributes(self):
        reader = LocalNetCDFDatasetReader(
            filepath=self.nc_standard_path,
            field_type="ocean_currents"
        )
        with reader:
            self.assertEqual(reader.resolved_u_var, "eastward_current")
            self.assertEqual(reader.resolved_v_var, "northward_current")
            self.assertEqual(reader.min_lat, 10.0)
            self.assertEqual(reader.max_lat, 20.0)
            self.assertEqual(reader.min_lon, 70.0)
            self.assertEqual(reader.max_lon, 80.0)
            self.assertEqual(len(reader.time_datetimes), 3)

    def test_missing_latitude_variable_raises_error(self):
        ds_invalid = self.ds_standard.drop_vars("latitude")
        bad_path = os.path.join(self.test_dir, "no_lat.nc")
        ds_invalid.to_netcdf(bad_path)

        reader = LocalNetCDFDatasetReader(bad_path)
        with self.assertRaises(InvalidDatasetError):
            reader.open_dataset()

    def test_missing_longitude_variable_raises_error(self):
        ds_invalid = self.ds_standard.drop_vars("longitude")
        bad_path = os.path.join(self.test_dir, "no_lon.nc")
        ds_invalid.to_netcdf(bad_path)

        reader = LocalNetCDFDatasetReader(bad_path)
        with self.assertRaises(InvalidDatasetError):
            reader.open_dataset()

    def test_missing_time_variable_raises_error(self):
        ds_invalid = self.ds_standard.drop_vars("time")
        bad_path = os.path.join(self.test_dir, "no_time.nc")
        ds_invalid.to_netcdf(bad_path)

        reader = LocalNetCDFDatasetReader(bad_path)
        with self.assertRaises(InvalidDatasetError):
            reader.open_dataset()

    def test_missing_u_component_raises_error(self):
        ds_invalid = self.ds_standard.drop_vars("eastward_current")
        bad_path = os.path.join(self.test_dir, "no_u.nc")
        ds_invalid.to_netcdf(bad_path)

        reader = LocalNetCDFDatasetReader(bad_path)
        with self.assertRaises(InvalidDatasetError):
            reader.open_dataset()

    def test_missing_v_component_raises_error(self):
        ds_invalid = self.ds_standard.drop_vars("northward_current")
        bad_path = os.path.join(self.test_dir, "no_v.nc")
        ds_invalid.to_netcdf(bad_path)

        reader = LocalNetCDFDatasetReader(bad_path)
        with self.assertRaises(InvalidDatasetError):
            reader.open_dataset()

    def test_invalid_dimensions_raises_error(self):
        u_bad = np.zeros((3, 6, 6))
        v_bad = np.zeros((3, 4, 6))
        ds_mismatch = xr.Dataset(
            data_vars={
                "u": (["time", "lat", "lon"], u_bad),
                "v": (["time", "lat_bad", "lon"], v_bad),
            },
            coords={
                "time": self.times,
                "lat": self.lats,
                "lat_bad": np.arange(4),
                "lon": self.lons,
            }
        )
        bad_path = os.path.join(self.test_dir, "mismatch_dim.nc")
        ds_mismatch.to_netcdf(bad_path)

        reader = LocalNetCDFDatasetReader(bad_path)
        with self.assertRaises(InvalidDatasetError):
            reader.open_dataset()

    def test_spatial_bilinear_interpolation_exactness(self):
        # Query at exact middle: lat=15.0 (midway 14 and 16), lon=75.0 (midway 74 and 76)
        # at time t0 (2026-09-01T00:00:00Z)
        # Expected u = 0.1 * 15.0 + 0.01 * 75.0 + 0 = 1.5 + 0.75 = 2.25
        # Expected v = 0.05 * 15.0 - 0.02 * 75.0 - 0 = 0.75 - 1.50 = -0.75
        reader = LocalNetCDFDatasetReader(self.nc_standard_path)
        with reader:
            u_interp, v_interp = reader.interpolate(
                latitude=15.0,
                longitude=75.0,
                timestamp="2026-09-01T00:00:00Z"
            )
            self.assertAlmostEqual(u_interp, 2.25, places=4)
            self.assertAlmostEqual(v_interp, -0.75, places=4)

    def test_temporal_linear_interpolation_exactness(self):
        # Query at grid node lat=10.0, lon=70.0 at time midway between t0 and t1:
        # t = 2026-09-01T03:00:00Z (t_fraction = 0.5)
        # at t0 (t_idx=0): u = 0.1*10 + 0.01*70 + 0 = 1.70
        # at t1 (t_idx=1): u = 0.1*10 + 0.01*70 + 0.05*1 = 1.75
        # midway expected u = 1.725
        reader = LocalNetCDFDatasetReader(self.nc_standard_path)
        with reader:
            u_interp, v_interp = reader.interpolate(
                latitude=10.0,
                longitude=70.0,
                timestamp="2026-09-01T03:00:00Z"
            )
            self.assertAlmostEqual(u_interp, 1.725, places=4)

    def test_combined_spatial_and_temporal_interpolation(self):
        # lat=15.0, lon=75.0 at t=2026-09-01T03:00:00Z (midway between t0 and t1)
        # at t0: u = 2.25
        # at t1: u = 0.1*15.0 + 0.01*75.0 + 0.05*1 = 2.30
        # midway expected u = 2.275
        reader = LocalNetCDFDatasetReader(self.nc_standard_path)
        with reader:
            u_interp, v_interp = reader.interpolate(
                latitude=15.0,
                longitude=75.0,
                timestamp="2026-09-01T03:00:00Z"
            )
            self.assertAlmostEqual(u_interp, 2.275, places=4)

    def test_out_of_domain_coordinates_raises_error(self):
        reader = LocalNetCDFDatasetReader(self.nc_standard_path)
        with reader:
            # Lat outside [10, 20]
            with self.assertRaises(OutOfDomainError):
                reader.interpolate(latitude=25.0, longitude=75.0, timestamp="2026-09-01T00:00:00Z")

            # Lon outside [70, 80]
            with self.assertRaises(OutOfDomainError):
                reader.interpolate(latitude=15.0, longitude=65.0, timestamp="2026-09-01T00:00:00Z")

    def test_out_of_range_timestamp_raises_error(self):
        reader = LocalNetCDFDatasetReader(self.nc_standard_path)
        with reader:
            # Prior to dataset start
            with self.assertRaises(TemporalCoverageError):
                reader.interpolate(
                    latitude=15.0,
                    longitude=75.0,
                    timestamp="2026-08-31T23:00:00Z"
                )
            # Past dataset end
            with self.assertRaises(TemporalCoverageError):
                reader.interpolate(
                    latitude=15.0,
                    longitude=75.0,
                    timestamp="2026-09-01T15:00:00Z"
                )

    def test_descending_latitude_dataset(self):
        desc_lats = np.arange(20.0, 8.0, -2.0)
        u_desc = np.zeros((1, len(desc_lats), len(self.lons)))
        v_desc = np.zeros((1, len(desc_lats), len(self.lons)))

        for i, lat in enumerate(desc_lats):
            for j, lon in enumerate(self.lons):
                u_desc[0, i, j] = 0.1 * lat
                v_desc[0, i, j] = 0.2 * lat

        ds_desc = xr.Dataset(
            data_vars={
                "u": (["time", "lat", "lon"], u_desc),
                "v": (["time", "lat", "lon"], v_desc),
            },
            coords={
                "time": [self.times[0]],
                "lat": desc_lats,
                "lon": self.lons,
            }
        )
        desc_path = os.path.join(self.test_dir, "desc_lat.nc")
        ds_desc.to_netcdf(desc_path)

        reader = LocalNetCDFDatasetReader(desc_path)
        with reader:
            u_val, v_val = reader.interpolate(latitude=15.0, longitude=75.0, timestamp="2026-09-01T00:00:00Z")
            self.assertAlmostEqual(u_val, 1.5, places=4)
            self.assertAlmostEqual(v_val, 3.0, places=4)

    def test_0_to_360_longitude_dataset(self):
        lons_360 = np.arange(280.0, 292.0, 2.0)  # spans [-80, -68] in [-180, 180]
        u_360 = np.zeros((1, len(self.lats), len(lons_360)))
        v_360 = np.zeros((1, len(self.lats), len(lons_360)))

        for i, lat in enumerate(self.lats):
            for j, lon in enumerate(lons_360):
                u_360[0, i, j] = 1.0 + 0.01 * lon
                v_360[0, i, j] = 2.0

        ds_360 = xr.Dataset(
            data_vars={
                "u": (["time", "lat", "lon"], u_360),
                "v": (["time", "lat", "lon"], v_360),
            },
            coords={
                "time": [self.times[0]],
                "lat": self.lats,
                "lon": lons_360,
            }
        )
        p360 = os.path.join(self.test_dir, "lon_360.nc")
        ds_360.to_netcdf(p360)

        reader = LocalNetCDFDatasetReader(p360)
        with reader:
            self.assertEqual(reader.lon_convention, "[0, 360]")
            # Query using [-180, 180] equivalent: lon = -75.0 -> normalized to 285.0
            u_val, _ = reader.interpolate(latitude=14.0, longitude=-75.0, timestamp="2026-09-01T00:00:00Z")
            self.assertAlmostEqual(u_val, 3.85, places=3)

    def test_local_currents_and_wind_providers(self):
        curr_provider = LocalCurrentsProvider(self.nc_standard_path)
        sample = curr_provider.get_current(
            latitude=14.0,
            longitude=74.0,
            timestamp="2026-09-01T00:00:00Z"
        )
        self.assertIsInstance(sample, CurrentSample)
        self.assertEqual(sample.latitude, 14.0)
        self.assertEqual(sample.longitude, 74.0)
        self.assertAlmostEqual(sample.u_current_mps, 0.1 * 14.0 + 0.01 * 74.0)
        self.assertAlmostEqual(sample.v_current_mps, 0.05 * 14.0 - 0.02 * 74.0)

        # Provider reuse / caching verification
        sample2 = curr_provider.get_current(
            latitude=16.0,
            longitude=76.0,
            timestamp="2026-09-01T06:00:00Z"
        )
        self.assertIsInstance(sample2, CurrentSample)
        curr_provider.close()

    def test_mock_providers_and_patterns(self):
        # Uniform mock currents
        mock_c = MockCurrentsProvider(const_u=0.5, const_v=0.2, pattern="uniform")
        s_c = mock_c.get_current(18.0, 72.0, "2026-09-02T12:00:00Z")
        self.assertEqual(s_c.u_current_mps, 0.5)
        self.assertEqual(s_c.v_current_mps, 0.2)

        # Vortex mock currents
        mock_vortex = MockCurrentsProvider(pattern="vortex", center_lat=18.0, center_lon=72.0)
        s_vortex = mock_vortex.get_current(18.2, 72.0, "2026-09-02T12:00:00Z")
        self.assertNotEqual(s_vortex.u_current_mps, 0.0)

        # Mock wind cyclonic
        mock_w = MockWindProvider(pattern="cyclonic", center_lat=18.0, center_lon=72.0)
        s_w = mock_w.get_wind(18.0, 72.5, "2026-09-02T12:00:00Z")
        self.assertIsInstance(s_w, WindSample)
        self.assertNotEqual(s_w.v_wind_mps, 0.0)

    def test_remote_adapters_raise_clear_error_when_unconfigured(self):
        copernicus = CopernicusCurrentsProvider()
        with self.assertRaises(EnvironmentalDataUnavailableError):
            copernicus.get_current(18.0, 72.0, "2026-09-02T12:00:00Z")

        hycom = HYCOMCurrentsProvider()
        with self.assertRaises(EnvironmentalDataUnavailableError):
            hycom.get_current(18.0, 72.0, "2026-09-02T12:00:00Z")

        era5 = ERA5WindProvider()
        with self.assertRaises(EnvironmentalDataUnavailableError):
            era5.get_wind(18.0, 72.0, "2026-09-02T12:00:00Z")

        gfs = GFSWindProvider()
        with self.assertRaises(EnvironmentalDataUnavailableError):
            gfs.get_wind(18.0, 72.0, "2026-09-02T12:00:00Z")


if __name__ == "__main__":
    unittest.main()
