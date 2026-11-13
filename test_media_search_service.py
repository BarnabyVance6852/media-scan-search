from types import SimpleNamespace

from media_search_service import DocumentRequest, MediaSearchService, SearchRequest


class FakeGateway:
    def __init__(self):
        self.saved = []
    def ocr(self, pdf, request_id):
        return {"text": "Host Ada interviewed engineer Lin about radio archives."}
    def upsert(self, collection, vectors, request_id):
        self.saved.extend(vectors)
        return {"count": len(vectors)}
    def query(self, collection, embedding, top_k=5):
        return {"matches": [{"metadata": {"text": self.saved[0]["metadata"]["text"]}}]}


class FakeEmbedder:
    embeddings = SimpleNamespace(create=lambda **kwargs: SimpleNamespace(data=[SimpleNamespace(embedding=[0.1, 0.2])]))


def test_ingest_then_search_returns_indexed_media_snippet(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"pdf")
    service = MediaSearchService(FakeGateway(), FakeEmbedder())
    result = service.ingest(DocumentRequest("scan-1", str(pdf)))
    answer = service.search(SearchRequest("Who hosted the interview?"))
    assert result == {"document_id": "scan-1", "chunks_indexed": 1}
    assert "Host Ada" in answer["snippets"][0]
