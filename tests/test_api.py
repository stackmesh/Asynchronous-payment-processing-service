import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_health_is_public(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_payments_require_api_key(client: TestClient) -> None:
    response = client.post("/api/v1/payments", json={})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing API key"


def test_invalid_api_key_is_rejected(client: TestClient) -> None:
    response = client.get(
        "/api/v1/payments/3fa85f64-5717-4562-b3fc-2c963f66afa6",
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 401


def test_validation_error_does_not_need_a_database(client: TestClient) -> None:
    response = client.post(
        "/api/v1/payments",
        headers={"X-API-Key": settings.api_key, "Idempotency-Key": "order-1"},
        json={"amount": "10.00", "currency": "GBP", "webhook_url": "https://merchant.example/hook"},
    )
    assert response.status_code == 422
