from universal_ai_studio.config.settings import get_settings


def test_settings_cache_can_be_refreshed_after_runtime_configuration(monkeypatch):
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://first:9200")
    get_settings.cache_clear()
    assert get_settings().elasticsearch_url == "http://first:9200"
    monkeypatch.setenv("ELASTICSEARCH_URL", "http://second:9200")
    get_settings.cache_clear()
    assert get_settings().elasticsearch_url == "http://second:9200"
    get_settings.cache_clear()
