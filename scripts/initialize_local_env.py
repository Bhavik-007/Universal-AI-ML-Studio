"""Create a local .env file and initialize encrypted-settings key if needed."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile


def initialize_env_file(env_path: Path, example_path: Path) -> tuple[bool, bool]:
    """Return (created_env_file, generated_encryption_key). Never print secrets."""
    created_env = False
    if not env_path.exists():
        if not example_path.is_file():
            raise FileNotFoundError(f"Environment template not found: {example_path}")
        env_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
        created_env = True

    lines = env_path.read_text(encoding="utf-8").splitlines()
    key_index = next((i for i, line in enumerate(lines) if line.strip().startswith("UAS_CONFIG_ENCRYPTION_KEY=")), None)
    current_key = ""
    if key_index is not None:
        current_key = lines[key_index].split("=", 1)[1].strip()
    if current_key:
        return created_env, False

    from cryptography.fernet import Fernet
    generated = Fernet.generate_key().decode("ascii")
    setting = f"UAS_CONFIG_ENCRYPTION_KEY={generated}"
    if key_index is None:
        lines.extend(["", "# Automatically generated local key for encrypted integration settings.", setting])
    else:
        lines[key_index] = setting

    content = "\n".join(lines).rstrip() + "\n"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".env.", suffix=".tmp", dir=env_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, env_path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return created_env, True


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    created_env, generated_key = initialize_env_file(root / ".env", root / ".env.example")
    print("Created local .env from .env.example." if created_env else "Existing .env preserved.")
    print("Generated a local encryption key for UI-managed integration credentials." if generated_key else "Existing encryption key retained.")
    print("Keep .env private and back up UAS_CONFIG_ENCRYPTION_KEY separately from config/secrets.enc.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
