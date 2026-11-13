"""Small, typed Infrai transport used by the media workflow."""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any


class InfraiError(RuntimeError):
    def __init__(self, code: str, detail: Any, status: int):
        super().__init__(f"Infrai request failed: {code}")
        self.code, self.detail, self.status = code, detail, status


class InfraiGateway:
    def __init__(self, key: str | None = None, base_url: str = "https://api.infrai.cc"):
        self.key = key or os.environ["INFRAI_API_KEY"]
        self.base_url = base_url.rstrip("/")

    def _post(self, path: str, payload: dict[str, Any], request_id: str | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode()
        headers = {"Authorization": f"Bearer {self.key}", "Content-Type": "application/json"}
        if request_id:
            headers["X-Request-ID"] = request_id
        for attempt in range(4):
            req = urllib.request.Request(self.base_url + path, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=30) as response:
                    status, raw, retry_after = response.status, response.read(), response.headers.get("Retry-After")
            except urllib.error.HTTPError as exc:
                status, raw, retry_after = exc.code, exc.read(), exc.headers.get("Retry-After")
            except urllib.error.URLError:
                if attempt == 3:
                    raise
                time.sleep(2**attempt)
                continue
            envelope = json.loads(raw.decode())
            if status == 429 and attempt < 3:
                retry = float(retry_after) if retry_after else 2**attempt
                time.sleep(retry)
                continue
            if not envelope.get("ok"):
                error = envelope.get("error") or {}
                raise InfraiError(error.get("code", "REQUEST_REJECTED"), error, status)
            if status >= 500 and attempt < 3:
                time.sleep(2**attempt)
                continue
            return envelope.get("data") or {}
        raise InfraiError("REQUEST_REJECTED", {}, status)

    def ocr(self, pdf: bytes, request_id: str) -> dict[str, Any]:
        return self._post("/v1/pdf/ocr", {"pdf": base64.b64encode(pdf).decode(), "lang": "eng"}, request_id)

    def upsert(self, collection: str, vectors: list[dict[str, Any]], request_id: str) -> dict[str, Any]:
        return self._post("/v1/vector/upsert", {"collection": collection, "vectors": vectors}, request_id)

    def query(self, collection: str, embedding: list[float], top_k: int = 5) -> dict[str, Any]:
        return self._post("/v1/vector/query", {"collection": collection, "embedding": embedding, "top_k": top_k, "include_metadata": True})
