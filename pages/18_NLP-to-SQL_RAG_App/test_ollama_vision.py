import json
import os
import urllib.request

from dotenv import load_dotenv


def main() -> None:
    load_dotenv()
    base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
    vision_model = os.getenv("OLLAMA_VISION_MODEL", "llava")

    print(f"Ollama URL: {base_url}")
    print(f"Required vision model: {vision_model}")

    try:
        with urllib.request.urlopen(f"{base_url}/api/tags", timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        print("FAILED: Ollama is not reachable.")
        print(str(exc))
        print("\nStart Ollama, then retry:")
        print("ollama serve")
        return

    models = [item.get("name", "") for item in data.get("models", [])]
    print("\nInstalled Ollama models:")
    if models:
        for model in models:
            print(f"- {model}")
    else:
        print("- none")

    model_roots = {model.split(":")[0] for model in models}
    if vision_model.split(":")[0] not in model_roots:
        print("\nFAILED: Required vision model is not installed.")
        print(f"Run: ollama pull {vision_model}")
        return

    print("\nSUCCESS: Ollama is reachable and the configured vision model is installed.")


if __name__ == "__main__":
    main()
