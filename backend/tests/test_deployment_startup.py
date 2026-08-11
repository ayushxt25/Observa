from pathlib import Path


def test_backend_dockerfile_runs_migrations_before_uvicorn() -> None:
    dockerfile = Path(__file__).resolve().parents[1] / "Dockerfile"
    content = dockerfile.read_text(encoding="utf-8")
    assert "alembic upgrade head && uvicorn" in content
