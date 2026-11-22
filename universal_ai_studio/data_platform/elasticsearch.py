"""Shared Elasticsearch-only vector store for Universal AI Studio.

No in-memory or third-party vector database fallback is provided: if Elasticsearch
is unavailable, indexing/retrieval fails explicitly instead of silently losing data.
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from typing import Any, Protocol


class ElasticsearchClient(Protocol):
    def index(self, *, index: str, id: str, document: dict[str, Any], refresh: bool = False) -> Any: ...
    def search(self, *, index: str, query: dict[str, Any], size: int) -> Any: ...


class ElasticsearchConfigurationError(RuntimeError):
    pass


def create_elasticsearch_client(url: str | None = None):
    """Create an authenticated Elasticsearch client from environment settings."""
    try:
        from elasticsearch import Elasticsearch
    except ImportError as exc:
        raise ElasticsearchConfigurationError(
            "Install the Elasticsearch client with: pip install 'elasticsearch>=8,<9'."
        ) from exc

    url = url or os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    api_key = os.getenv("ELASTICSEARCH_API_KEY")
    username = os.getenv("ELASTICSEARCH_USERNAME")
    password = os.getenv("ELASTICSEARCH_PASSWORD")
    verify_certs = os.getenv("ELASTICSEARCH_VERIFY_CERTS", "true").lower() not in {"0", "false", "no"}
    timeout = float(os.getenv("ELASTICSEARCH_TIMEOUT_SECONDS", "20"))

    kwargs: dict[str, Any] = {
        "hosts": [url],
        "verify_certs": verify_certs,
        "request_timeout": timeout,
        "max_retries": 2,
        "retry_on_timeout": True,
    }
    if api_key:
        kwargs["api_key"] = api_key
    elif username and password:
        kwargs["basic_auth"] = (username, password)
    return Elasticsearch(**kwargs)


@dataclass
class ElasticsearchVectorStore:
    index: str
    dimensions: int
    client: Any | None = None
    url: str | None = None
    text_field: str = "text"
    vector_field: str = "embedding"

    def __post_init__(self) -> None:
        if not self.index or not self.index.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Invalid Elasticsearch index name.")
        if self.dimensions < 1:
            raise ValueError("Embedding dimensions must be positive.")
        if self.client is None:
            self.client = create_elasticsearch_client(self.url)
        self.ensure_index()

    def ensure_index(self) -> None:
        if self.client.indices.exists(index=self.index):
            mapping = self.client.indices.get_mapping(index=self.index)
            props = mapping[self.index].get("mappings", {}).get("properties", {})
            vector_mapping = props.get(self.vector_field, {})
            if vector_mapping.get("type") != "dense_vector":
                raise ElasticsearchConfigurationError(
                    f"Index '{self.index}' does not define '{self.vector_field}' as dense_vector."
                )
            existing_dims = vector_mapping.get("dims")
            if existing_dims is not None and int(existing_dims) != self.dimensions:
                raise ElasticsearchConfigurationError(
                    f"Index '{self.index}' uses {existing_dims} dimensions; configured model emits {self.dimensions}."
                )
            return
        self.client.indices.create(
            index=self.index,
            mappings={
                "dynamic": True,
                "properties": {
                    self.text_field: {"type": "text"},
                    self.vector_field: {
                        "type": "dense_vector",
                        "dims": self.dimensions,
                        "index": True,
                        "similarity": "cosine",
                    },
                    "metadata": {"type": "object", "dynamic": True},
                    "created_at": {"type": "date"},
                },
            },
        )

    def index_document(
        self,
        document_id: str,
        text: str,
        embedding: list[float],
        metadata: dict[str, Any] | None = None,
        *,
        refresh: bool = False,
    ) -> Any:
        if len(embedding) != self.dimensions:
            raise ValueError(
                f"Embedding dimension mismatch: expected {self.dimensions}, received {len(embedding)}."
            )
        return self.client.index(
            index=self.index,
            id=document_id,
            document={
                self.text_field: text,
                self.vector_field: embedding,
                "metadata": metadata or {},
            },
            refresh=refresh,
        )

    def search(
        self,
        query_text: str,
        query_vector: list[float],
        *,
        top_k: int = 5,
        filters: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        if len(query_vector) != self.dimensions:
            raise ValueError(
                f"Query vector dimension mismatch: expected {self.dimensions}, received {len(query_vector)}."
            )
        if top_k < 1 or top_k > 100:
            raise ValueError("top_k must be between 1 and 100.")
        filter_clauses = [
            {"term": {f"metadata.{key}": value}} for key, value in (filters or {}).items()
        ]
        query = {
            "bool": {
                "should": [
                    {"match": {self.text_field: {"query": query_text}}},
                    {
                        "knn": {
                            "field": self.vector_field,
                            "query_vector": query_vector,
                            "k": top_k,
                            "num_candidates": max(top_k * 10, 50),
                        }
                    },
                ],
                "minimum_should_match": 1,
                "filter": filter_clauses,
            }
        }
        response = self.client.search(index=self.index, query=query, size=top_k)
        hits = response.get("hits", {}).get("hits", [])
        output = []
        for hit in hits:
            source = hit.get("_source", {})
            output.append(
                {
                    "text": source.get(self.text_field, ""),
                    "metadata": source.get("metadata", {}),
                    "score": hit.get("_score", 0.0),
                }
            )
        return output

    def count(self) -> int:
        return int(self.client.count(index=self.index).get("count", 0))


@dataclass
class ElasticsearchRetrievalService:
    client: ElasticsearchClient
    index: str

    def index_chunk(self, chunk_id: str, text: str, embedding: list[float], metadata: dict[str, Any]) -> Any:
        return self.client.index(
            index=self.index,
            id=chunk_id,
            document={"text": text, "embedding": embedding, "metadata": metadata},
        )

    def hybrid_search(self, query_text: str, query_vector: list[float], size: int = 5) -> Any:
        query = {
            "bool": {
                "should": [
                    {"match": {"text": {"query": query_text}}},
                    {"knn": {"field": "embedding", "query_vector": query_vector, "k": size, "num_candidates": max(size * 10, 50)}},
                ],
                "minimum_should_match": 1,
            }
        }
        return self.client.search(index=self.index, query=query, size=size)
