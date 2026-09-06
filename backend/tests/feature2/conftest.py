"""
Pytest configuration and shared test fixtures for Feature 2.
"""

from datetime import datetime
import os
from pathlib import Path
import sys
import pytest

# Ensure clean imports under new package location
_backend_dir = Path(__file__).resolve().parent.parent.parent
_app_dir = _backend_dir / "app"
_tests_dir = _backend_dir / "tests"
_f2_tests_dir = _tests_dir / "feature2"

for _p in [str(_backend_dir), str(_app_dir), str(_f2_tests_dir)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

try:
    import app.feature2
    sys.modules.setdefault("feature2", app.feature2)
except Exception:
    pass

try:
    import tests.feature2.fixtures as _f2_fixtures
    sys.modules.setdefault("tests.fixtures", _f2_fixtures)
    import tests.feature2.fixtures.environment as _f2_env
    sys.modules.setdefault("tests.fixtures.environment", _f2_env)
    import tests.feature2.fixtures.environment.create_fixtures as _f2_create
    sys.modules.setdefault("tests.fixtures.environment.create_fixtures", _f2_create)
except Exception:
    pass

from feature2.schemas.input_schema import SlickDetectionInput, CentroidCoordinates, GeoJSONGeometry
from feature2.config import Feature2Settings
from feature2.data.currents.mock import MockCurrentsProvider
from feature2.data.wind.mock import MockWindProvider


@pytest.fixture
def mock_sar_slick_input() -> SlickDetectionInput:
    """Fixture providing a valid SAR oil slick detection payload from Feature 1."""
    return SlickDetectionInput(
        spill_id="SAR-TEST-2026-001",
        observation_time=datetime.fromisoformat("2026-09-02T12:00:00"),
        area_sq_km=5.4,
        perimeter_km=14.2,
        centroid=CentroidCoordinates(latitude=18.9219, longitude=72.8347),
        geometry=GeoJSONGeometry(
            type="Polygon",
            coordinates=[
                [
                    [72.8200, 18.9100],
                    [72.8500, 18.9100],
                    [72.8500, 18.9350],
                    [72.8200, 18.9350],
                    [72.8200, 18.9100]
                ]
            ]
        ),
        metadata={
            "satellite": "Sentinel-1A",
            "polarization": "VV",
            "wind_speed_ms": 4.5
        }
    )


@pytest.fixture
def test_settings() -> Feature2Settings:
    """Fixture providing isolated configuration settings for testing."""
    return Feature2Settings(
        environment="testing",
        random_seed=123
    )


@pytest.fixture
def mock_currents():
    return MockCurrentsProvider(const_u=0.20, const_v=0.10)


@pytest.fixture
def mock_wind():
    return MockWindProvider(const_u=4.0, const_v=2.0)
