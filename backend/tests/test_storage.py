from app.storage import (
    append_jsonl,
    atomic_write_json,
    atomic_write_jsonl,
    read_jsonl,
    sanitize_text,
)


def test_json_storage_round_trip(tmp_path) -> None:
    path = tmp_path / "records.jsonl"
    append_jsonl(path, {"a": 1})
    append_jsonl(path, {"a": 2})
    assert read_jsonl(path) == [{"a": 1}, {"a": 2}]
    atomic_write_jsonl(path, [{"a": 3}])
    assert read_jsonl(path) == [{"a": 3}]
    manifest = tmp_path / "manifest.json"
    atomic_write_json(manifest, {"status": "completed"})
    assert '"completed"' in manifest.read_text(encoding="utf-8")


def test_sanitize_text_removes_sensitive_provider_metadata() -> None:
    raw = (
        'api_key=sk-secret {"user_id":"user-secret",'
        '"Authorization":"Bearer auth-secret"} C:\\Users\\person\\result.json'
    )
    sanitized = sanitize_text(raw, secrets=("sk-secret",))
    assert "sk-secret" not in sanitized
    assert "user-secret" not in sanitized
    assert "auth-secret" not in sanitized
    assert "C:\\Users\\person" not in sanitized
    assert sanitized.count("[redacted]") == 3
    assert "[local-path]" in sanitized
