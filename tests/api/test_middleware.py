"""Guardian regression tests for the ASGI middleware.

G-007: unmatched paths (404 scans) must not mint a new Prometheus label value
per URL — that is unbounded label cardinality, i.e. a memory-growth DoS on
the in-process registry.

G-008: the client-supplied X-Request-Id is echoed into responses and bound into
every log line, so it must be length/charset-bounded.
"""

from __future__ import annotations

import uuid

from fastapi.testclient import TestClient

from deepCab.api.app import create_app
from deepCab.obs.prom import http_request_duration_seconds


def _route_labels() -> set[str]:
    out: set[str] = set()
    for metric in http_request_duration_seconds.collect():
        for sample in metric.samples:
            if "route" in sample.labels:
                out.add(sample.labels["route"])
    return out


def test_unmatched_paths_share_one_route_label() -> None:
    with TestClient(create_app()) as client:
        paths = [f"/no-such-{uuid.uuid4().hex}" for _ in range(5)]
        for p in paths:
            assert client.get(p).status_code == 404
        labels = _route_labels()
    assert not any(p in labels for p in paths)


def test_request_id_is_echoed_when_well_formed() -> None:
    with TestClient(create_app()) as client:
        r = client.get("/", headers={"X-Request-Id": "abc-123_DEF"})
    assert r.headers["X-Request-Id"] == "abc-123_DEF"


def test_request_id_is_replaced_when_oversized_or_malformed() -> None:
    with TestClient(create_app()) as client:
        for bad in ("x" * 500, "a b<script>", "id;drop"):
            r = client.get("/", headers={"X-Request-Id": bad})
            rid = r.headers["X-Request-Id"]
            assert rid != bad
            assert 0 < len(rid) <= 64
