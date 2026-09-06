"""
Offline Deterministic Demo Pipeline for Feature 2.
Executes end-to-end Feature 2 pipeline using local environmental fixtures
and real georeferenced Sentinel-1 SAR scene fixtures without external network credentials.
Clearly labeled as: OFFLINE DEMO / LOCAL FIXTURE DATA.
"""

from datetime import datetime, timezone
import json
import os
from typing import Any, Dict, Optional, Tuple

from ..config import Feature2Settings, BackwardTracingConfig, ForecastConfig
from ..data.wind.era5 import ERA5WindProvider
from ..data.currents.copernicus import CopernicusCurrentsProvider, CopernicusForecastCurrentsProvider
from ..data.wind.gfs import GFSWindProvider
from ..forecast.forecaster import ForwardForecaster
from ..origin.estimator import OriginEstimator
from ..output.formatter import OutputFormatter
from ..pipeline.service import Feature2PipelineService
from ..schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry
from ..schemas.output_schema import UnifiedFeature2Result, Feature2PipelineResponse
from ..simulation.forward.engine import ForwardSimulationEngine


def get_default_demo_fixtures(project_root: str) -> Dict[str, str]:
    """Returns local paths to demo environmental NetCDF fixture files."""
    env_dir = os.path.join(project_root, "tests", "fixtures", "environment")
    return {
        "historical_wind": os.path.join(env_dir, "north_sea_era5_2018.nc"),
        "historical_currents": os.path.join(env_dir, "north_sea_copernicus_2018.nc"),
        "forecast_wind": os.path.join(env_dir, "north_sea_forecast_wind_2018.nc"),
        "forecast_currents": os.path.join(env_dir, "north_sea_copernicus_2018.nc"),
    }


def load_demo_slick_input(project_root: str) -> SlickDetectionInput:
    """
    Loads Feature 1 slick detection input.
    Uses real georeferenced Zenodo Sentinel-1 scene if available; otherwise fallback fixture.
    """
    tiff_path = os.path.join(project_root, "tests", "fixtures", "Oil", "00000.tif")
    mask_path = os.path.join(project_root, "tests", "fixtures", "Mask_oil", "00000.tif")

    if os.path.exists(tiff_path) and os.path.exists(mask_path):
        from scripts.validate_real_scene import inspect_sentinel1_geotiff, derive_feature1_output_from_mask
        meta = inspect_sentinel1_geotiff(tiff_path)
        slick = derive_feature1_output_from_mask(mask_path, meta)
        slick.metadata["demo_mode"] = "OFFLINE DEMO / LOCAL FIXTURE DATA"
        return slick

    # Synthetic fallback fixture if raw TIFF is not present
    return SlickDetectionInput(
        spill_id="DEMO_SENTINEL1_OFFSHORE_SLICK_001",
        observation_time="2018-08-03T17:25:57Z",
        centroid=CentroidCoordinates(latitude=55.241575, longitude=4.053477),
        area_sq_km=1.4539,
        perimeter_km=8.0,
        geometry=GeoJSONGeometry(
            type="Polygon",
            coordinates=[[
                [4.02118, 55.15008],
                [4.12044, 55.15008],
                [4.06340, 55.24126],
                [4.06322, 55.24144],
                [4.02118, 55.15008]
            ]]
        ),
        metadata={
            "demo_mode": "OFFLINE DEMO / LOCAL FIXTURE DATA",
            "scene_origin": "Central North Sea SAR observation"
        }
    )


def create_demo_pipeline_service(
    project_root: str,
    random_seed: int = 42,
    custom_fixture_paths: Optional[Dict[str, str]] = None
) -> Feature2PipelineService:
    """Initializes and returns a Feature2PipelineService wired to offline demo fixtures."""
    fixtures = custom_fixture_paths or get_default_demo_fixtures(project_root)

    demo_settings = Feature2Settings(
        environment="demo",
        random_seed=random_seed,
        backward=BackwardTracingConfig(
            max_backtrack_hours=72.0,
            candidate_time_step_hours=3.0,
            particles_per_slick=30,
            simulation_step_seconds=300
        ),
        forecast=ForecastConfig(
            forecast_horizons_hours=[6.0, 12.0, 24.0, 48.0],
            particles_per_slick=30,
            forecast_ensemble_size=1,
            simulation_step_seconds=600
        )
    )

    hist_wind = ERA5WindProvider(data_path=fixtures["historical_wind"])
    hist_curr = CopernicusCurrentsProvider(data_path=fixtures["historical_currents"])
    fc_wind = GFSWindProvider(data_path=fixtures["forecast_wind"])
    fc_curr = CopernicusForecastCurrentsProvider(data_path=fixtures["forecast_currents"])

    origin_estimator = OriginEstimator(
        currents_provider=hist_curr,
        wind_provider=hist_wind,
        settings=demo_settings
    )

    fwd_engine = ForwardSimulationEngine(
        currents_provider=fc_curr,
        wind_provider=fc_wind,
        settings=demo_settings
    )

    forecaster = ForwardForecaster(
        simulation_engine=fwd_engine,
        settings=demo_settings
    )

    return Feature2PipelineService(
        origin_estimator=origin_estimator,
        forecaster=forecaster,
        settings=demo_settings
    )


def run_offline_demo(
    project_root: Optional[str] = None,
    output_dir: Optional[str] = None,
    random_seed: int = 42,
) -> Tuple[UnifiedFeature2Result, Dict[str, Any]]:
    """
    Executes complete offline demo:
      1. Loads real Sentinel-1 fixture
      2. Runs Feature2PipelineService with offline environmental slices
      3. Produces UnifiedFeature2Result
      4. Produces GeoJSON FeatureCollection
      5. Optionally exports result files to output_dir
    """
    root = project_root or os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    slick = load_demo_slick_input(root)
    service = create_demo_pipeline_service(root, random_seed=random_seed)

    pipeline_res: Feature2PipelineResponse = service.run_pipeline(slick)
    unified_res: UnifiedFeature2Result = pipeline_res.to_unified_result()
    geojson_data: Dict[str, Any] = OutputFormatter.unified_result_to_geojson(unified_res)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        unified_path = os.path.join(output_dir, "demo_unified_result.json")
        geojson_path = os.path.join(output_dir, "demo_pipeline.geojson")

        with open(unified_path, "w", encoding="utf-8") as f:
            json.dump(unified_res.model_dump(mode="json"), f, indent=2)

        with open(geojson_path, "w", encoding="utf-8") as f:
            json.dump(geojson_data, f, indent=2)

    return unified_res, geojson_data
