import importlib

import pytest

from universal_ai_studio.applications import registry as default_registry
from universal_ai_studio.applications import registry as registry_instance
from universal_ai_studio.applications.registry import ApplicationRegistry
registry_module = importlib.import_module("universal_ai_studio.applications.registry")


def test_discovery_registers_existing_page_as_disabled_by_default(monkeypatch, tmp_path):
    monkeypatch.setattr(registry_module, "ROOT", tmp_path)
    entry = tmp_path / "pages" / "custom_app.py"
    entry.parent.mkdir(parents=True)
    entry.write_text("import streamlit as st\nst.title('Custom')\n", encoding="utf-8")
    registry = ApplicationRegistry()
    app = registry.register_manifest(key="custom_app", name="Custom App", path="pages/custom_app.py")
    assert app.discovered is True
    assert app.available is True
    assert app.enabled is False
    assert (tmp_path / "config" / "modules" / "custom_app.json").is_file()
    registry.refresh_discovered()
    assert registry.get("custom_app").path == "pages/custom_app.py"


def test_discovery_rejects_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setattr(registry_module, "ROOT", tmp_path)
    registry = ApplicationRegistry()
    with pytest.raises(ValueError, match="relative Python file path"):
        registry.register_manifest(key="unsafe_module", name="Unsafe", path="../outside.py")


def test_builtin_registry_remains_unchanged():
    assert len(default_registry.list()) == 18
    assert len(registry_instance.list()) == 18


def test_custom_module_dependency_manifest_is_validated(monkeypatch, tmp_path):
    from universal_ai_studio.core.dependency_manager import validate_module_dependencies
    monkeypatch.setattr(registry_module, "ROOT", tmp_path)
    entry = tmp_path / "pages" / "custom_app.py"
    entry.parent.mkdir(parents=True)
    entry.write_text("# custom page\n", encoding="utf-8")
    registry = ApplicationRegistry()
    app = registry.register_manifest(
        key="custom_app", name="Custom App", path="pages/custom_app.py", dependencies=("package_that_does_not_exist_uas",)
    )
    ready, missing = validate_module_dependencies(app.key, app.dependencies)
    assert ready is False
    assert "package_that_does_not_exist_uas" in missing
