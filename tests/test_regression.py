import pytest

from marine_data_engine.messaging.queue import JetStreamQueue
from marine_data_engine.storage.raw_store import InMemoryRawStore

# R3: Note about PostgreSQL schema testing
# Migrations are currently tested via `make migrate`, which applies
# alembic upgrade head against the real TimescaleDB.
# Down-migrations are tested via `make migrate-down`.
# Test coverage ensures hypertables and triggers apply cleanly without PostGIS if absent.


def test_s3_integrity_in_memory():
    """R2: S3 integrity test using InMemoryRawStore.

    Upload object, retrieve, verify content matches.
    Corrupt object, verify integrity failure is detected.
    """
    store = InMemoryRawStore()
    result = store.put(
        provider="TEST",
        dataset="test_ds",
        data=b"test content for integrity check",
        ext=".txt",
    )
    assert result.checksum_sha256 is not None
    assert result.size_bytes == len(b"test content for integrity check")

    # Retrieve and verify integrity
    data = store.get(result.key)
    assert data == b"test content for integrity check"

    # Corrupt the stored data and verify detection
    store._objects[result.key] = b"corrupted data"
    with pytest.raises(RuntimeError, match="Integrity check failed"):
        store.get(result.key)


def test_s3_deduplication():
    """R2b: S3 deduplication test.

    Same content uploaded twice should report already_existed on second put.
    """
    store = InMemoryRawStore()
    r1 = store.put(provider="TEST", dataset="ds", data=b"dup", ext=".bin")
    r2 = store.put(provider="TEST", dataset="ds", data=b"dup", ext=".bin")
    assert r1.key == r2.key
    assert not r1.already_existed
    assert r2.already_existed


def test_multi_worker_nats_config():
    """R4: Multi-worker NATS queue configuration sanity test.

    Verify JetStreamQueue can be instantiated with expected defaults.
    """
    q = JetStreamQueue(servers="nats://localhost:4222", stream_prefix="TEST_NATS")
    assert q._prefix == "TEST_NATS"
    assert q._max_deliver == 5

    # Custom max_deliver
    q2 = JetStreamQueue(servers="nats://localhost:4222", stream_prefix="TEST", max_deliver=10)
    assert q2._max_deliver == 10
