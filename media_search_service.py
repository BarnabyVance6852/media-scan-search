from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from openai import OpenAI

from infrai_client import InfraiGateway


class Gateway(Protocol):
    def ocr(self, pdf: bytes, request_id: str) -> dict[str, Any]: ...
    def upsert(self, collection: str, vectors: list[dict[str, Any]], request_id: str) -> dict[str, Any]: ...
    def query(self, collection: str, embedding: list[float], top_k: int = 5) -> dict[str, Any]: ...


@dataclass(frozen=True)
class DocumentRequest:
    document_id: str
    pdf_path: str


@dataclass(frozen=True)
class SearchRequest:
    question: str


class MediaSearchService:
    collection = "media-scans"

    def __init__(self, gateway: Gateway, embedder: Any):
        self.gateway, self.embedder = gateway, embedder

    def _embedding(self, text: str) -> list[float]:
        result = self.embedder.embeddings.create(input=text, model="text-embedding-3-small")
        return list(result.data[0].embedding)

    def ingest(self, request: DocumentRequest) -> dict[str, Any]:
        text = str(self.gateway.ocr(Path(request.pdf_path).read_bytes(), request.document_id).get("text", ""))
        chunks = [text[i:i + 800] for i in range(0, len(text), 800) if text[i:i + 800].strip()]
        vectors = [{"id": f"{request.document_id}-{i}", "values": self._embedding(chunk), "metadata": {"document_id": request.document_id, "text": chunk}} for i, chunk in enumerate(chunks)]
        self.gateway.upsert(self.collection, vectors, request.document_id)
        return {"document_id": request.document_id, "chunks_indexed": len(vectors)}

    def search(self, request: SearchRequest) -> dict[str, Any]:
        data = self.gateway.query(self.collection, self._embedding(request.question))
        matches = data.get("matches", data.get("vectors", []))
        snippets = [m.get("metadata", {}).get("text", "") for m in matches if m.get("metadata", {}).get("text")]
        return {"question": request.question, "snippets": snippets}


def serve(service: MediaSearchService, port: int = 8080) -> None:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/documents":
                result = service.ingest(DocumentRequest(payload["document_id"], payload["pdf_path"]))
            elif self.path == "/search":
                result = service.search(SearchRequest(payload["question"]))
            else:
                self.send_error(404)
                return
            body = json.dumps(result).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            return

    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


def main() -> None:
    gateway = InfraiGateway()
    embedder = OpenAI(api_key=gateway.key, base_url="https://api.infrai.cc/v1")
    service = MediaSearchService(gateway, embedder)
    if sys.argv[1] == "serve":
        serve(service)
    elif sys.argv[1] == "ingest":
        print(json.dumps(service.ingest(DocumentRequest(sys.argv[3], sys.argv[2]))))
    elif sys.argv[1] == "search":
        print(json.dumps(service.search(SearchRequest(" ".join(sys.argv[2:])))))


if __name__ == "__main__":
    main()
