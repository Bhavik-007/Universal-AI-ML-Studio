from pathlib import Path

from universal_ai_studio.applications import registry

ROOT = Path(__file__).resolve().parents[2]


def test_registry_has_unique_keys_and_paths():
    applications = registry.list()
    assert len({app.key for app in applications}) == len(applications)
    assert all(app.path for app in applications)


def test_registered_application_paths_exist():
    assert all((ROOT / app.path).is_file() for app in registry.list())


def test_registry_covers_all_eighteen_legacy_apps():
    assert len(registry.list()) == 18


def test_every_registered_module_has_a_dependency_manifest():
    from universal_ai_studio.core.dependency_manager import MODULE_DEPENDENCIES
    assert set(app.key for app in registry.list()) == set(MODULE_DEPENDENCIES)


def test_builtin_applications_have_navigation_metadata():
    applications = registry.list()
    assert all(app.icon and app.description and app.url_path == app.key for app in applications)
    assert len({app.url_path for app in applications}) == len(applications)


def test_email_campaign_workflow_is_registered_under_marketing_not_as_a_mail_client():
    marketing = registry.get("marketing")
    assert marketing is not None
    assert "email campaign" in marketing.description.lower()
    assert registry.get("mail") is None
