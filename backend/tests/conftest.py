"""
Root test configuration for backend test suite.
Ensures backend, app, and feature2 packages are cleanly accessible in sys.path
and sys.modules without requiring manual alterations to production imports.
"""

import os
import sys
from pathlib import Path

# Paths
backend_dir = Path(__file__).resolve().parent.parent
app_dir = backend_dir / "app"
tests_dir = backend_dir / "tests"
tests_f2_dir = tests_dir / "feature2"

for p in [str(backend_dir), str(app_dir), str(tests_f2_dir)]:
    if p not in sys.path:
        sys.path.insert(0, p)

# Alias sys.modules['feature2'] to app.feature2
try:
    import app.feature2
    sys.modules["feature2"] = app.feature2
except Exception:
    pass

# Alias tests.fixtures to tests.feature2.fixtures for compatibility
try:
    import tests.feature2.fixtures as _f2_fixtures
    sys.modules.setdefault("tests.fixtures", _f2_fixtures)
    import tests.feature2.fixtures.environment as _f2_env
    sys.modules.setdefault("tests.fixtures.environment", _f2_env)
    import tests.feature2.fixtures.environment.create_fixtures as _f2_create
    sys.modules.setdefault("tests.fixtures.environment.create_fixtures", _f2_create)
except Exception:
    pass
