import pytest

from universal_ai_studio.data_platform.elasticsearch import ElasticsearchVectorStore


class FakeIndices:
    def __init__(self):
        self.created = None

    def exists(self, index):
        return False

    def create(self, **kwargs):
        self.created = kwargs
        return {"acknowledged": True}


class FakeClient:
    def __init__(self):
        self.indices = FakeIndices()
        self.documents = {}
        self.last_query = None

    def index(self, *, index, id, document, refresh=False):
        self.documents[id] = document
        return {"result": "created"}

    def search(self, *, index, query, size):
        self.last_query = query
        return {"hits": {"hits": [{"_score": 1.0, "_source": self.documents["doc-1"]}]}}

    def count(self, *, index):
        return {"count": len(self.documents)}


def test_elasticsearch_vector_store_creates_dense_vector_mapping():
    client = FakeClient()
    store = ElasticsearchVectorStore(index="uas_test", dimensions=3, client=client)
    mapping = client.indices.created["mappings"]["properties"]["embedding"]
    assert mapping["type"] == "dense_vector"
    assert mapping["dims"] == 3
    assert mapping["index"] is True


def test_elasticsearch_vector_store_validates_embedding_dimensions():
    store = ElasticsearchVectorStore(index="uas_test", dimensions=3, client=FakeClient())
    with pytest.raises(ValueError, match="dimension mismatch"):
        store.index_document("doc-1", "hello", [0.1, 0.2], {})


def test_elasticsearch_hybrid_search_combines_keyword_and_vector_retrieval():
    client = FakeClient()
    store = ElasticsearchVectorStore(index="uas_test", dimensions=3, client=client)
    store.index_document("doc-1", "hello world", [0.1, 0.2, 0.3], {"tenant_id": "t1"})
    results = store.search("hello", [0.1, 0.2, 0.3], top_k=2, filters={"tenant_id": "t1"})
    clauses = client.last_query["bool"]["should"]
    assert any("match" in clause for clause in clauses)
    assert any("knn" in clause for clause in clauses)
    assert results[0]["text"] == "hello world"
    assert client.last_query["bool"]["filter"] == [{"term": {"metadata.tenant_id": "t1"}}]
