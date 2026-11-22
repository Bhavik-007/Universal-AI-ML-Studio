import logging
from sentence_transformers import SentenceTransformer

from nlp_to_sql_app.core.config import config
from universal_ai_studio.data_platform.elasticsearch import ElasticsearchVectorStore


class SchemaRetriever:
    """Retrieve approved SQL schema context from Elasticsearch vector search."""

    def __init__(self):
        es_settings = config.settings.get("elasticsearch", {})
        self.index = es_settings.get("schema_index", "uas_schema_metadata")
        self.model = SentenceTransformer(
            es_settings.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
        )
        self.vector_store = None
        self.available = False
        try:
            self.vector_store = ElasticsearchVectorStore(
                index=self.index,
                dimensions=int(es_settings.get("embedding_dimensions", 384)),
                url=config.elasticsearch_url,
            )
            self.available = True
            self.index_tables()
        except Exception:
            logging.exception("Elasticsearch schema retrieval initialization failed.")

    def get_relevant_schema(self, query: str, top_k: int = 3) -> str:
        if not self.available or self.vector_store is None:
            return self._yaml_schema_context()
        try:
            vector = self.model.encode(query, normalize_embeddings=True).tolist()
            results = self.vector_store.search(query, vector, top_k=top_k)
            relevant = [item.get("text", "") for item in results if item.get("text")]
            return "\n\n".join(relevant) if relevant else self._yaml_schema_context()
        except Exception:
            logging.exception("Elasticsearch schema search failed; using configured schema context.")
            return self._yaml_schema_context()

    def index_tables(self) -> None:
        if not self.available or self.vector_store is None:
            return
        for name, details in (config.tables.get("tables") or {}).items():
            full_name = details.get("full_name", name)
            schema = details.get("schema", "dbo")
            relationships = self._format_relationships(details.get("relationships", []))
            text = (
                f"Table: {full_name}. Schema: {schema}. Logical name: {name}. "
                f"Columns: {details.get('allowed_columns', [])}. "
                f"Info: {details.get('description', '')}. {relationships} "
                f"Use {full_name} in SQL queries."
            )
            embedding = self.model.encode(text, normalize_embeddings=True).tolist()
            self.vector_store.index_document(
                document_id=f"schema-{name}",
                text=text,
                embedding=embedding,
                metadata={"record_type": "schema", "table": full_name},
            )

    @staticmethod
    def _yaml_schema_context() -> str:
        schema_lines = []
        for name, details in (config.tables.get("tables") or {}).items():
            full_name = details.get("full_name", name)
            schema = details.get("schema", "dbo")
            relationships = SchemaRetriever._format_relationships(details.get("relationships", []))
            schema_lines.append(
                f"Table: {full_name}. Schema: {schema}. Logical name: {name}. "
                f"Columns: {details.get('allowed_columns', [])}. "
                f"Info: {details.get('description', '')}. {relationships} "
                f"Use {full_name} in SQL queries."
            )
        return "\n\n".join(schema_lines)

    @staticmethod
    def _format_relationships(relationships: list[dict]) -> str:
        return " ".join(
            "Relationship: "
            f"{item.get('from_column')} joins to "
            f"{item.get('to_table')}.{item.get('to_column')}."
            for item in relationships
        )
