from fastapi.testclient import TestClient

from riskweave_api.main import app


def test_health_endpoint_reports_ready(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://riskweave:password@postgres:5432/riskweave")
    monkeypatch.setenv("NEO4J_URI", "bolt://neo4j:7687")
    monkeypatch.setenv("NEO4J_USER", "neo4j")
    monkeypatch.setenv("NEO4J_PASSWORD", "password")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
