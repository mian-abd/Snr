from app.storage import append_jsonl, atomic_write_json, atomic_write_jsonl, read_jsonl


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
