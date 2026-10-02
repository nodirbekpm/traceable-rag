from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from anchor.api.main import app
from anchor.db import get_session


def test_health_reports_ok_when_database_answers() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_health_reports_degraded_when_database_is_unreachable() -> None:
    # Port 1 is never a Postgres server, so the connection attempt fails fast.
    dead_engine = create_engine(
        "postgresql+psycopg://anchor:anchor@127.0.0.1:1/anchor",
        connect_args={"connect_timeout": 1},
    )

    def dead_session() -> Iterator[Session]:
        with Session(dead_engine) as session:
            yield session

    app.dependency_overrides[get_session] = dead_session
    try:
        with TestClient(app) as client:
            response = client.get("/health")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["database"] == "unreachable"
