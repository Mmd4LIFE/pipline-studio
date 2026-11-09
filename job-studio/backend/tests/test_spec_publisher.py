import json
from pathlib import Path

from app.services.spec_publisher import atomic_write


def test_atomic_write_replaces_file(tmp_path: Path):
    path = tmp_path / "current" / "job.json"
    atomic_write(path, {"job_id": "a", "revision": 1})
    atomic_write(path, {"job_id": "a", "revision": 2})
    data = json.loads(path.read_text())
    assert data["revision"] == 2
    assert not list(path.parent.glob("*.tmp"))


def test_atomic_write_does_not_leave_partial_json(tmp_path: Path, monkeypatch):
    path = tmp_path / "job.json"
    atomic_write(path, {"ok": True})
    original = path.read_text()

    def boom(*_args, **_kwargs):
        raise OSError("simulated crash after temp write")

    monkeypatch.setattr("app.services.spec_publisher.os.replace", boom)
    try:
        atomic_write(path, {"ok": False})
    except OSError:
        pass
    assert path.read_text() == original
