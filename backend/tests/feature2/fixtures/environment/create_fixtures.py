"""
Utility to generate small, deterministic NetCDF fixture datasets for environmental data testing (Task 4).
Uses predictable analytical fields for exact bilinear and temporal interpolation validation.
"""

from datetime import datetime, timedelta, timezone
import os
from typing import Dict
import numpy as np
import pandas as pd
import xarray as xr


FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))


def safe_to_netcdf(ds: xr.Dataset, filepath: str) -> None:
    """Saves xarray dataset to NetCDF, gracefully handling Windows file-lock PermissionErrors."""
    try:
        ds.to_netcdf(filepath)
    except PermissionError:
        pass


def generate_all_fixtures(target_dir: str = FIXTURES_DIR) -> Dict[str, str]:
    """Generates all standard fixture NetCDF files in the target directory."""
    os.makedirs(target_dir, exist_ok=True)
    paths: Dict[str, str] = {}

    # 1. ERA5 Small Historical Wind (Arabian Gulf region, August 2026)
    # Analytical formula: u10 = 5.0 + 0.1*(lat - 24) + 0.05*(lon - 53) + 0.1*t_step
    #                     v10 = 2.0 + 0.05*(lat - 24) - 0.02*(lon - 53) - 0.05*t_step
    lats_era5 = np.linspace(24.0, 26.0, 5)   # 24.0, 24.5, 25.0, 25.5, 26.0
    lons_era5 = np.linspace(53.0, 55.0, 5)   # 53.0, 53.5, 54.0, 54.5, 55.0
    times_era5 = pd.date_range("2026-08-27T00:00:00", periods=5, freq="3h")

    nt_e = len(times_era5)
    nlat_e = len(lats_era5)
    nlon_e = len(lons_era5)

    u10_data = np.zeros((nt_e, nlat_e, nlon_e), dtype=np.float32)
    v10_data = np.zeros((nt_e, nlat_e, nlon_e), dtype=np.float32)

    for t_idx in range(nt_e):
        for i, lat in enumerate(lats_era5):
            for j, lon in enumerate(lons_era5):
                u10_data[t_idx, i, j] = 5.0 + 0.1 * (lat - 24.0) + 0.05 * (lon - 53.0) + 0.1 * t_idx
                v10_data[t_idx, i, j] = 2.0 + 0.05 * (lat - 24.0) - 0.02 * (lon - 53.0) - 0.05 * t_idx

    ds_era5 = xr.Dataset(
        data_vars={
            "u10": (["time", "latitude", "longitude"], u10_data),
            "v10": (["time", "latitude", "longitude"], v10_data),
        },
        coords={
            "time": times_era5,
            "latitude": lats_era5,
            "longitude": lons_era5,
        },
        attrs={"title": "ERA5 Small Synthetic Test Fixture", "source": "ECMWF"}
    )
    era5_path = os.path.join(target_dir, "era5_small.nc")
    safe_to_netcdf(ds_era5, era5_path)
    paths["era5"] = era5_path

    # 2. Copernicus Small Historical Currents (4D dataset with depth dimension)
    # Analytical formula: uo = 0.3 + 0.02*(lat - 24) + 0.01*(lon - 53) + 0.02*t_step
    #                     vo = 0.1 + 0.01*(lat - 24) - 0.01*(lon - 53) - 0.01*t_step
    lats_cop = np.linspace(24.0, 26.0, 5)
    lons_cop = np.linspace(53.0, 55.0, 5)
    depths_cop = np.array([0.494], dtype=np.float32)
    times_cop = pd.date_range("2026-08-26T00:00:00", periods=9, freq="12h")

    nt_c = len(times_cop)
    ndepth_c = len(depths_cop)
    nlat_c = len(lats_cop)
    nlon_c = len(lons_cop)

    uo_data = np.zeros((nt_c, ndepth_c, nlat_c, nlon_c), dtype=np.float32)
    vo_data = np.zeros((nt_c, ndepth_c, nlat_c, nlon_c), dtype=np.float32)

    for t_idx in range(nt_c):
        for i, lat in enumerate(lats_cop):
            for j, lon in enumerate(lons_cop):
                uo_data[t_idx, 0, i, j] = 0.3 + 0.02 * (lat - 24.0) + 0.01 * (lon - 53.0) + 0.02 * t_idx
                vo_data[t_idx, 0, i, j] = 0.1 + 0.01 * (lat - 24.0) - 0.01 * (lon - 53.0) - 0.01 * t_idx

    ds_cop = xr.Dataset(
        data_vars={
            "uo": (["time", "depth", "latitude", "longitude"], uo_data, {"units": "m s**-1", "long_name": "Eastward water velocity"}),
            "vo": (["time", "depth", "latitude", "longitude"], vo_data, {"units": "m s**-1", "long_name": "Northward water velocity"}),
        },
        coords={
            "time": times_cop,
            "depth": depths_cop,
            "latitude": lats_cop,
            "longitude": lons_cop,
        },
        attrs={"title": "Copernicus Small Synthetic Surface Currents Fixture", "source": "CMEMS"}
    )
    cop_path = os.path.join(target_dir, "copernicus_small.nc")
    safe_to_netcdf(ds_cop, cop_path)
    paths["copernicus"] = cop_path

    # 3. GFS Operational Forecast Wind (+0h to +48h)
    times_gfs = pd.date_range("2026-08-27T06:00:00", periods=9, freq="6h")
    nt_g = len(times_gfs)

    u10_gfs = np.zeros((nt_g, nlat_e, nlon_e), dtype=np.float32)
    v10_gfs = np.zeros((nt_g, nlat_e, nlon_e), dtype=np.float32)

    for t_idx in range(nt_g):
        for i, lat in enumerate(lats_era5):
            for j, lon in enumerate(lons_era5):
                u10_gfs[t_idx, i, j] = 4.0 + 0.05 * (lat - 24.0) + 0.02 * (lon - 53.0) + 0.05 * t_idx
                v10_gfs[t_idx, i, j] = 1.5 - 0.02 * (lat - 24.0) + 0.03 * (lon - 53.0) + 0.02 * t_idx

    ds_gfs = xr.Dataset(
        data_vars={
            "u10": (["time", "latitude", "longitude"], u10_gfs, {"units": "m s**-1"}),
            "v10": (["time", "latitude", "longitude"], v10_gfs, {"units": "m s**-1"}),
        },
        coords={
            "time": times_gfs,
            "latitude": lats_era5,
            "longitude": lons_era5,
        },
        attrs={"title": "GFS Small Synthetic Forecast Wind Fixture", "source": "NOAA NCEP"}
    )
    gfs_path = os.path.join(target_dir, "forecast_wind_small.nc")
    safe_to_netcdf(ds_gfs, gfs_path)
    paths["gfs"] = gfs_path

    # 4. Descending Latitude Fixture (ERA5 format: North to South)
    lats_desc = np.linspace(26.0, 24.0, 5) # 26.0 down to 24.0
    u_desc = np.ones((len(times_era5), len(lats_desc), len(lons_era5)), dtype=np.float32) * 6.0
    v_desc = np.ones((len(times_era5), len(lats_desc), len(lons_era5)), dtype=np.float32) * 3.0
    ds_desc = xr.Dataset(
        data_vars={
            "u10": (["time", "latitude", "longitude"], u_desc),
            "v10": (["time", "latitude", "longitude"], v_desc),
        },
        coords={
            "time": times_era5,
            "latitude": lats_desc,
            "longitude": lons_era5,
        }
    )
    desc_path = os.path.join(target_dir, "era5_descending_lat.nc")
    safe_to_netcdf(ds_desc, desc_path)
    paths["descending_lat"] = desc_path

    # 5. Longitude [0, 360] Fixture (South Pacific / Peru: lon ~282 to 284)
    lats_peru = np.linspace(-13.0, -11.0, 5)
    lons_360 = np.linspace(282.0, 284.0, 5) # -78 to -76 converted to [0, 360]
    u_360 = np.ones((len(times_era5), len(lats_peru), len(lons_360)), dtype=np.float32) * 2.5
    v_360 = np.ones((len(times_era5), len(lats_peru), len(lons_360)), dtype=np.float32) * -1.0
    ds_360 = xr.Dataset(
        data_vars={
            "uo": (["time", "latitude", "longitude"], u_360),
            "vo": (["time", "latitude", "longitude"], v_360),
        },
        coords={
            "time": times_era5,
            "latitude": lats_peru,
            "longitude": lons_360,
        }
    )
    lon360_path = os.path.join(target_dir, "copernicus_lon360.nc")
    safe_to_netcdf(ds_360, lon360_path)
    paths["lon360"] = lon360_path

    # 6. Real Scene North Sea 2018-08-03 Fixtures (covering Zenodo Scene 00000, 72h historical + 48h forecast)
    lats_ns = np.linspace(53.0, 57.5, 10)
    lons_ns = np.linspace(1.5, 6.5, 11)

    # ERA5 Historical Wind (2018-07-31 12:00 to 2018-08-04 06:00, covering T0 - 72h to T0)
    times_ns_hist = pd.date_range("2018-07-31T12:00:00", periods=16, freq="6h")
    u_ns_era5 = np.ones((len(times_ns_hist), len(lats_ns), len(lons_ns)), dtype=np.float32) * 4.5
    v_ns_era5 = np.ones((len(times_ns_hist), len(lats_ns), len(lons_ns)), dtype=np.float32) * 2.5
    ds_ns_era5 = xr.Dataset(
        data_vars={"u10": (["time", "latitude", "longitude"], u_ns_era5), "v10": (["time", "latitude", "longitude"], v_ns_era5)},
        coords={"time": times_ns_hist, "latitude": lats_ns, "longitude": lons_ns},
        attrs={"title": "North Sea ERA5 Slice August 2018 (72h historical coverage)"}
    )
    ns_era5_path = os.path.join(target_dir, "north_sea_era5_2018.nc")
    safe_to_netcdf(ds_ns_era5, ns_era5_path)
    paths["north_sea_era5"] = ns_era5_path

    # Copernicus Surface Currents (2018-07-31 12:00 to 2018-08-06 06:00, covering 72h historical + 48h forecast)
    times_ns_cop = pd.date_range("2018-07-31T12:00:00", periods=24, freq="6h")
    uo_ns_cop = np.ones((len(times_ns_cop), 1, len(lats_ns), len(lons_ns)), dtype=np.float32) * 0.25
    vo_ns_cop = np.ones((len(times_ns_cop), 1, len(lats_ns), len(lons_ns)), dtype=np.float32) * 0.15
    ds_ns_cop = xr.Dataset(
        data_vars={"uo": (["time", "depth", "latitude", "longitude"], uo_ns_cop), "vo": (["time", "depth", "latitude", "longitude"], vo_ns_cop)},
        coords={"time": times_ns_cop, "depth": np.array([0.494], dtype=np.float32), "latitude": lats_ns, "longitude": lons_ns},
        attrs={"title": "North Sea Copernicus Currents Slice August 2018 (72h hist + 48h fc)"}
    )
    ns_cop_path = os.path.join(target_dir, "north_sea_copernicus_2018.nc")
    safe_to_netcdf(ds_ns_cop, ns_cop_path)
    paths["north_sea_copernicus"] = ns_cop_path

    # GFS / Forecast Wind (+0h to +48h)
    times_ns_fc = pd.date_range("2018-08-03T12:00:00", periods=12, freq="6h")
    u_ns_fc = np.ones((len(times_ns_fc), len(lats_ns), len(lons_ns)), dtype=np.float32) * 5.0
    v_ns_fc = np.ones((len(times_ns_fc), len(lats_ns), len(lons_ns)), dtype=np.float32) * 2.0
    ds_ns_fc = xr.Dataset(
        data_vars={"u10": (["time", "latitude", "longitude"], u_ns_fc), "v10": (["time", "latitude", "longitude"], v_ns_fc)},
        coords={"time": times_ns_fc, "latitude": lats_ns, "longitude": lons_ns},
        attrs={"title": "North Sea Forecast Wind Slice August 2018"}
    )
    ns_fc_path = os.path.join(target_dir, "north_sea_forecast_wind_2018.nc")
    safe_to_netcdf(ds_ns_fc, ns_fc_path)
    paths["north_sea_forecast_wind"] = ns_fc_path

    return paths


if __name__ == "__main__":
    generated = generate_all_fixtures()
    print(f"Generated {len(generated)} test fixture datasets:")
    for k, v in generated.items():
        print(f"  - {k}: {v} ({os.path.getsize(v)} bytes)")
