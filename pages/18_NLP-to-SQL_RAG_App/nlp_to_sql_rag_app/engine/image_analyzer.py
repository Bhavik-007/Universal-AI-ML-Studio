import base64
import io
import json
import os
import urllib.request

from nlp_to_sql_rag_app.core.config import config
from nlp_to_sql_rag_app.engine.document_loader import DocumentChunk


class ImageAnalyzer:
    IMAGE_TYPES = {"png", "jpg", "jpeg", "tif", "tiff"}

    def __init__(self):
        rag_settings = config.rag_settings.get("rag", {})
        image_settings = config.rag_settings.get("image_analysis", {})
        ollama_settings = config.settings.get("ollama", {})
        self.vision_model = os.getenv(
            "OLLAMA_VISION_MODEL",
            image_settings.get("vision_model", "llava"),
        )
        self.timeout = image_settings.get("timeout_seconds", 120)
        self.base_url = ollama_settings.get("base_url", "http://localhost:11434").rstrip("/")
        self.prompt = image_settings.get("prompt") or self._default_prompt()
        self.chunk_size = rag_settings.get("chunk_size", 900)
        self.chunk_overlap = rag_settings.get("chunk_overlap", 150)

    def can_analyze(self, file_name: str) -> bool:
        return self._extension(file_name) in self.IMAGE_TYPES

    def analyze_file(self, file_name: str, content: bytes) -> list[DocumentChunk]:
        extension = self._extension(file_name)
        if extension not in self.IMAGE_TYPES:
            raise ValueError(f"Unsupported image type: {extension}")

        image_payload, width, height = self._prepare_image(content)
        analysis = self._call_ollama_vision(image_payload, file_name, width, height)
        chunks = self._chunk_text(analysis)
        return [
            DocumentChunk(
                text=chunk,
                metadata={
                    "file_name": file_name,
                    "file_type": extension,
                    "content_type": "image_analysis",
                    "image_width": width,
                    "image_height": height,
                    "vision_model": self.vision_model,
                    "chunk_index": index,
                },
            )
            for index, chunk in enumerate(chunks)
        ]

    def _call_ollama_vision(self, image_payload: str, file_name: str, width: int, height: int) -> str:
        self._ensure_vision_model_available()
        payload = {
            "model": self.vision_model,
            "prompt": (
                f"File name: {file_name}\n"
                f"Image dimensions: {width}x{height}\n\n"
                f"{self.prompt}"
            ),
            "images": [image_payload],
            "stream": False,
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                "Image analysis failed while calling Ollama. "
                f"Check that Ollama is running and model '{self.vision_model}' supports image input. "
                f"Try: ollama pull {self.vision_model}"
            ) from exc

        analysis = (data.get("response") or "").strip()
        if not analysis:
            raise RuntimeError("Image analysis returned an empty response.")
        return analysis

    def _ensure_vision_model_available(self) -> None:
        request = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                data = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(
                "Ollama is not reachable. Start Ollama first, then retry image indexing."
            ) from exc

        available_models = {
            item.get("name", "").split(":")[0]
            for item in data.get("models", [])
            if item.get("name")
        }
        requested_model = self.vision_model.split(":")[0]
        if requested_model not in available_models:
            installed = ", ".join(sorted(available_models)) or "none"
            raise RuntimeError(
                f"Ollama vision model '{self.vision_model}' is not installed. "
                f"Installed models: {installed}. Run: ollama pull {self.vision_model}"
            )

    @staticmethod
    def _prepare_image(content: bytes) -> tuple[str, int, int]:
        try:
            from PIL import Image
        except ImportError as exc:
            raise ImportError("Install pillow to analyze uploaded images.") from exc

        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            output = io.BytesIO()
            image.convert("RGB").save(output, format="PNG")
            encoded = base64.b64encode(output.getvalue()).decode("utf-8")
        return encoded, width, height

    def _chunk_text(self, text: str) -> list[str]:
        clean_text = " ".join((text or "").split())
        if not clean_text:
            return []

        chunks = []
        start = 0
        while start < len(clean_text):
            end = start + self.chunk_size
            chunks.append(clean_text[start:end])
            if end >= len(clean_text):
                break
            start = max(end - self.chunk_overlap, start + 1)
        return chunks

    @staticmethod
    def _extension(file_name: str) -> str:
        return file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""

    @staticmethod
    def _default_prompt() -> str:
        return (
            "Analyze this uploaded business or technical visualization. Produce a structured semantic description "
            "that can be embedded for retrieval. Do not merely OCR visible text.\n\n"
            "Return these sections:\n"
            "1. Visualization type: classify as chart, graph, dashboard, spatial map, heatmap, engineering diagram, scientific plot, infographic, or other.\n"
            "2. Main subject: what the visualization is about.\n"
            "3. Visible entities and labels: axes, legends, categories, regions, metrics, annotations, units, and important text.\n"
            "4. Data patterns: trends, peaks, drops, clusters, correlations, anomalies, comparisons, and outliers.\n"
            "5. Analytical insights: business or technical interpretation of what the visual implies.\n"
            "6. Possible questions this image can answer.\n"
            "7. Limitations: any uncertainty due to resolution, missing labels, or unreadable content."
        )
