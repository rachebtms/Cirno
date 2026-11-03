"""Bounded OpenAI-compatible embeddings without a local inference runtime."""
from __future__ import annotations

import math

import httpx


class APIEmbeddingWorker:
    peak_mb = 0.0

    def __init__(self, config):
        self.config = config
        self.client = None
        self.dimensions = None

    def __enter__(self):
        if not self.config.embedding_api_base or not self.config.embedding_api_model.strip():
            raise ValueError("Configure the embedding API base URL and model in Memory retrieval settings")
        headers = {"Authorization": "Bearer " + self.config.embedding_api_key} if self.config.embedding_api_key else {}
        self.client = httpx.Client(timeout=self.config.embedding_timeout_seconds, headers=headers, follow_redirects=False)
        return self

    def request(self, texts, **options):
        try:
            return self._request(texts, **options)
        except (httpx.HTTPError, httpx.InvalidURL) as error:
            raise RuntimeError(f"Embedding API connection failed ({type(error).__name__}); using BM25") from error

    def _request(self, texts, **options):
        chunks, more = [], False
        if options.get("chunked"):
            content = texts[0]
            width = self.config.embedding_api_chunk_chars
            stride = width * 3 // 4
            count = (max(0, len(content) - 1) // stride) + 1
            first = options.get("start_chunk", 0)
            stop = min(count, first + options.get("max_chunks", 8))
            chunks = [{"chunk_index": index, "start_char": index * stride, "end_char": min(index * stride + width, len(content))} for index in range(first, stop)]
            texts = [content[chunk["start_char"]:chunk["end_char"]] for chunk in chunks]
            more = stop < count
        if not texts:
            return {"vectors": [], "chunks": chunks, "has_more": more}
        endpoint = self.config.embedding_api_base.rstrip("/")
        if not endpoint.endswith("/embeddings"):
            endpoint += "/embeddings"
        with self.client.stream("POST", endpoint, json={"model": self.config.embedding_api_model, "input": texts, "encoding_format": "float"}) as response:
            if response.status_code != 200:
                raise ValueError(f"Embedding API returned HTTP {response.status_code}; check its address, credentials and model")
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 16 * 1024 * 1024:
                    raise ValueError("Embedding API response exceeds 16 MB")
        import json
        result = json.loads(body)
        rows = result.get("data") if isinstance(result, dict) else None
        if not isinstance(rows, list) or len(rows) != len(texts):
            raise ValueError("Embedding API returned the wrong number of vectors")
        indexed = {}
        for row in rows:
            if not isinstance(row, dict) or type(row.get("index")) is not int or row['index'] in indexed:
                raise ValueError("Embedding API returned invalid vector indices")
            vector = row.get("embedding")
            if not isinstance(vector, list) or not vector or len(vector) > 65536 or any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
                raise ValueError("Embedding API must return finite numeric float vectors")
            norm = math.sqrt(sum(value * value for value in vector))
            if not norm or not math.isfinite(norm):
                raise ValueError("Embedding API returned an invalid vector norm")
            if self.dimensions is not None and self.dimensions != len(vector):
                raise ValueError("Embedding API changed vector dimensions during indexing")
            self.dimensions = len(vector)
            indexed[row['index']] = [value / norm for value in vector]
        if set(indexed) != set(range(len(texts))):
            raise ValueError("Embedding API returned missing or out-of-range vector indices")
        return {"vectors": [indexed[index] for index in range(len(texts))], "chunks": chunks, "has_more": more}

    def __exit__(self, *_):
        if self.client:
            self.client.close()
