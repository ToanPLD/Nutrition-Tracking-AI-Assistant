# core/services/retrieval/qdrant_rest_client.py
"""
Lightweight REST client for Qdrant using httpx.
Bypasses the C-extension dependency on grpc/cygrpc which can be blocked by
system Application Control policies on Windows environments.
"""

from typing import Any, Dict, List, Optional, Union
import httpx
from types import SimpleNamespace


class ScoredPoint:
    def __init__(self, id: Any, score: float, payload: Dict[str, Any], vector: Optional[Any] = None):
        self.id = id
        self.score = float(score)
        self.payload = payload or {}
        self.vector = vector

    def __repr__(self):
        return f"ScoredPoint(id={self.id}, score={self.score:.4f}, payload_keys={list(self.payload.keys())})"


class _ModelsNamespace:
    class Filter:
        def __init__(self, should: Optional[List[Any]] = None, must: Optional[List[Any]] = None, must_not: Optional[List[Any]] = None):
            self.should = should or []
            self.must = must or []
            self.must_not = must_not or []

        def to_dict(self):
            res = {}
            if self.should:
                res["should"] = [s.to_dict() if hasattr(s, "to_dict") else s for s in self.should]
            if self.must:
                res["must"] = [m.to_dict() if hasattr(m, "to_dict") else m for m in self.must]
            if self.must_not:
                res["must_not"] = [mn.to_dict() if hasattr(mn, "to_dict") else mn for mn in self.must_not]
            return res

    class FieldCondition:
        def __init__(self, key: str, match: Any = None):
            self.key = key
            self.match = match

        def to_dict(self):
            res = {"key": self.key}
            if self.match:
                if hasattr(self.match, "to_dict"):
                    res["match"] = self.match.to_dict()
                elif isinstance(self.match, dict):
                    res["match"] = self.match
                else:
                    res["match"] = {"value": self.match}
            return res

    class MatchText:
        def __init__(self, text: str):
            self.text = text

        def to_dict(self):
            return {"text": self.text}

    class MatchValue:
        def __init__(self, value: Any):
            self.value = value

        def to_dict(self):
            return {"value": self.value}

    class Distance:
        Cosine = "Cosine"
        Euclid = "Euclid"
        Dot = "Dot"

    class VectorParams:
        def __init__(self, size: int, distance: str = "Cosine"):
            self.size = size
            self.distance = distance


models = _ModelsNamespace()


class QdrantRestClient:
    """REST API Client for Qdrant, compatible with standard search operations."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: Optional[str] = None,
        prefer_grpc: bool = False,
        timeout: float = 15.0,
        **kwargs
    ):
        self.base_url = url.rstrip("/")
        self.api_key = api_key or ""
        self.timeout = timeout
        self.headers = {"Content-Type": "application/json"}
        if self.api_key:
            self.headers["api-key"] = self.api_key

    def _get_client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, headers=self.headers, timeout=self.timeout)

    def search(
        self,
        collection_name: str,
        query_vector: Any,
        limit: int = 5,
        query_filter: Any = None,
        with_payload: bool = True,
        **kwargs
    ) -> List[ScoredPoint]:
        # Handle tuple like ("text", vector)
        vec = query_vector
        if isinstance(query_vector, tuple) and len(query_vector) == 2:
            vec = query_vector[1]

        # Convert numpy array to list if needed
        if hasattr(vec, "tolist"):
            vec = vec.tolist()
        elif not isinstance(vec, list):
            vec = list(vec)

        body: Dict[str, Any] = {
            "vector": vec,
            "limit": int(limit),
            "with_payload": with_payload
        }

        if query_filter:
            if hasattr(query_filter, "to_dict"):
                body["filter"] = query_filter.to_dict()
            elif isinstance(query_filter, dict):
                body["filter"] = query_filter

        try:
            with self._get_client() as client:
                res = client.post(f"/collections/{collection_name}/points/search", json=body)
                if res.status_code != 200:
                    return []
                data = res.json().get("result", [])
                points = []
                for p in data:
                    points.append(
                        ScoredPoint(
                            id=p.get("id"),
                            score=p.get("score", 0.0),
                            payload=p.get("payload", {}) or {},
                            vector=p.get("vector")
                        )
                    )
                return points
        except Exception:
            return []

    def scroll(
        self,
        collection_name: str,
        scroll_filter: Any = None,
        limit: int = 5,
        with_payload: bool = True,
        with_vectors: bool = False,
        **kwargs
    ) -> Tuple[List[ScoredPoint], Optional[Any]]:
        body: Dict[str, Any] = {
            "limit": int(limit),
            "with_payload": with_payload,
            "with_vector": with_vectors
        }
        if scroll_filter:
            if hasattr(scroll_filter, "to_dict"):
                body["filter"] = scroll_filter.to_dict()
            elif isinstance(scroll_filter, dict):
                body["filter"] = scroll_filter

        try:
            with self._get_client() as client:
                res = client.post(f"/collections/{collection_name}/points/scroll", json=body)
                if res.status_code != 200:
                    return [], None
                data = res.json().get("result", {})
                points_raw = data.get("points", []) if isinstance(data, dict) else []
                next_offset = data.get("next_page_offset") if isinstance(data, dict) else None
                points = []
                for p in points_raw:
                    points.append(
                        ScoredPoint(
                            id=p.get("id"),
                            score=1.0,
                            payload=p.get("payload", {}) or {},
                            vector=p.get("vector")
                        )
                    )
                return points, next_offset
        except Exception:
            return [], None

    def get_collections(self):
        try:
            with self._get_client() as client:
                res = client.get("/collections")
                if res.status_code == 200:
                    collections_list = res.json().get("result", {}).get("collections", [])
                    return SimpleNamespace(collections=[SimpleNamespace(name=c["name"]) for c in collections_list])
        except Exception:
            pass
        return SimpleNamespace(collections=[])
