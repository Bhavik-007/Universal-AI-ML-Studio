"""Central feature flags for application modules and platform capabilities."""
from __future__ import annotations

from universal_ai_studio.core.configuration import load_platform_config, save_platform_config


def is_feature_enabled(feature_key: str, default: bool = True) -> bool:
    return bool(load_platform_config().get("features", {}).get(feature_key, default))


def enabled_features() -> dict[str, bool]:
    return {key: bool(value) for key, value in load_platform_config().get("features", {}).items()}


def set_feature_enabled(feature_key: str, enabled: bool) -> None:
    config = load_platform_config()
    if feature_key not in config.get("features", {}):
        raise KeyError(f"Unknown feature: {feature_key}")
    config["features"][feature_key] = bool(enabled)
    save_platform_config(config)
