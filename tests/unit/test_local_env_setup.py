from pathlib import Path

from cryptography.fernet import Fernet

from scripts.initialize_local_env import initialize_env_file


def test_env_setup_creates_local_file_and_encryption_key(tmp_path):
    template = tmp_path / ".env.example"
    env = tmp_path / ".env"
    template.write_text("UAS_ENVIRONMENT=development\nUAS_CONFIG_ENCRYPTION_KEY=\n", encoding="utf-8")
    created, generated = initialize_env_file(env, template)
    assert created is True
    assert generated is True
    key_line = next(line for line in env.read_text(encoding="utf-8").splitlines() if line.startswith("UAS_CONFIG_ENCRYPTION_KEY="))
    Fernet(key_line.split("=", 1)[1].encode("ascii"))


def test_env_setup_preserves_existing_encryption_key(tmp_path):
    template = tmp_path / ".env.example"
    env = tmp_path / ".env"
    template.write_text("UAS_CONFIG_ENCRYPTION_KEY=\n", encoding="utf-8")
    existing_key = Fernet.generate_key().decode()
    env.write_text(f"UAS_CONFIG_ENCRYPTION_KEY={existing_key}\nCUSTOM_SETTING=keep\n", encoding="utf-8")
    created, generated = initialize_env_file(env, template)
    assert created is False
    assert generated is False
    assert f"UAS_CONFIG_ENCRYPTION_KEY={existing_key}" in env.read_text(encoding="utf-8")
    assert "CUSTOM_SETTING=keep" in env.read_text(encoding="utf-8")
