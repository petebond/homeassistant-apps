"""pytest config for the HA integration tests (needs pytest-homeassistant-custom-component)."""
from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"

OURS = str(Path(__file__).resolve().parent.parent / "integration" / "custom_components")


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    # The test harness ships its own custom_components package; add this app's
    # integration folder to its search path.
    import custom_components

    if OURS not in custom_components.__path__:
        custom_components.__path__.insert(0, OURS)
    yield
