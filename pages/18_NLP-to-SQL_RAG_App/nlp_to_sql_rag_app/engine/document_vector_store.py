import hashlib
import logging
import os

from sentence_transformers import SentenceTransformer

from nlp_to_sql_rag_app.core.config import config
from nlp_to_sql_rag_app.engine.document_loader import DocumentChunk
from universal_ai_studio.data_platform.elasticsearch import ElasticsearchVectorStore


class DocumentVectorStore:
    """Document chunk store backed exclusively by Elasticsearch."""

    def __init__(self):
        rag_settings = config.rag_settings.get("rag", {})
        es_settings = config.settings.get("elasticsearch", {})
        self.index = os.getenv(
            "ELASTICSEARCH_DOCUMENT_INDEX",
            rag_settings.get("index_name", es_settings.get("documents_index", "uas_document_chunks")),
        )
        model_name = es_settings.get(
            "embedding_model",
            "sentence-transformers/all-MiniLM-L6-v2",
        )
        self.model = SentenceTransformer(model_name)
        self.store = ElasticsearchVectorStore(
            index=self.index,
            dimensions=int(es_settings.get("embedding_dimensions", 384)),
            url=config.elasticsearch_url,
        )
        self.available = True

    def add_chunks(self, chunks: list[DocumentChunk]) -> int:
        if not chunks:
            return 0
        vectors = self.model.encode(
            [chunk.text for chunk in chunks],
            normalize_embeddings=True,
        ).tolist()
        for chunk, vector in zip(chunks, vectors):
            metadata = dict(chunk.metadata or {})
            file_name = str(metadata.get("file_name", metadata.get("source", "document")))
            chunk_index = str(metadata.get("chunk_index", "0"))
            stable_key = hashlib.sha256(
                f"{file_name}|{chunk_index}|{chunk.text}".encode("utf-8")
            ).hexdigest()
            self.store.index_document(
                document_id=stable_key,
                text=chunk.text,
                embedding=vector,
                metadata=metadata,
            )
        return len(chunks)

    def search(self, query: str, top_k: int = 4) -> list[dict]:
        query_vector = self.model.encode(
            query,
            normalize_embeddings=True,
        ).tolist()
        return self.store.search(query, query_vector, top_k=top_k)

    def has_content(self) -> bool:
        try:
            return self.store.count() > 0
        except Exception:
            logging.exception("Elasticsearch document count failed.")
            return False
