import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parent
SENSITIVE_KEYS = {"api_key", "access_token", "authorization", "secret", "full_prompt", "healthkit_raw_samples"}
EVENT_REQUIRED = {"type", "event_id", "payload_version", "run_id", "thread_id", "sequence", "timestamp", "payload"}
BLOCK_REQUIRED = {"id", "kind", "status", "revision", "order_key", "node_role", "payload"}
BLOCK_STATUSES = {"pending", "streaming", "ready", "failed"}


def _read(path: Path):
    return json.loads(path.read_text())


def _walk_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_keys(child)


def test_valid_events_have_envelope_and_unknown_event_is_allowed():
    events = [_read(path) for path in (ROOT / "valid/events").glob("*.json")]
    assert events
    for event in events:
        assert EVENT_REQUIRED <= event.keys()
        assert event["sequence"] > 0
    assert any(event["type"].startswith("future.") for event in events)


def test_valid_and_invalid_blocks_follow_status_contract():
    for path in (ROOT / "valid/blocks").glob("*.json"):
        block = _read(path)
        assert BLOCK_REQUIRED <= block.keys()
        assert block["status"] in BLOCK_STATUSES
    assert _read(ROOT / "invalid/blocks/bad_status.json")["status"] not in BLOCK_STATUSES


def test_invalid_event_is_rejected_by_required_field_check():
    assert not EVENT_REQUIRED <= _read(ROOT / "invalid/events/missing_sequence.json").keys()


def test_all_contract_fixtures_are_free_of_sensitive_keys():
    for path in (ROOT / "valid", ROOT / "invalid"):
        for fixture in path.rglob("*.json"):
            assert not SENSITIVE_KEYS.intersection(set(_walk_keys(_read(fixture)))), fixture


def test_manifest_hashes_match_schema_and_fixture_bytes():
    manifest = _read(ROOT / "manifest.json")
    for entry in manifest["files"]:
        path = ROOT / entry["path"]
        assert path.exists(), path
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == entry["sha256"], entry["path"]
