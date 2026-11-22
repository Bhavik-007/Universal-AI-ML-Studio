import pytest

from universal_ai_studio.core import configuration
from universal_ai_studio.integrations.manager import IntegrationDisabledError, IntegrationManager


def test_shared_integration_manager_blocks_disabled_integrations(monkeypatch, tmp_path):
    monkeypatch.setattr(configuration, "PLATFORM_CONFIG_PATH", tmp_path / "platform.json")
    config = configuration.load_platform_config()
    config["integrations"]["rest_api"].update(enabled=False)
    configuration.save_platform_config(config)
    manager = IntegrationManager()
    with pytest.raises(IntegrationDisabledError, match="rest_api.*disabled"):
        manager.create_rest_session()
