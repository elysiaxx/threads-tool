"""
Test ranh giới cách ly tenant của TenantRepository — phần quan trọng nhất về bảo
mật. Dùng collection giả (AsyncMock) để kiểm tra user_id luôn được chèn/đóng dấu,
không cần Mongo thật.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.repository import TenantRepository, TenantScopeError


def _repo(user_id="u1"):
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
    col.insert_many = AsyncMock(return_value=MagicMock(inserted_ids=["x"]))
    col.update_one = AsyncMock()
    col.count_documents = AsyncMock(return_value=0)
    agg = MagicMock()
    agg.to_list = AsyncMock(return_value=[])
    col.aggregate = MagicMock(return_value=agg)
    return TenantRepository(col, user_id), col


def test_empty_user_id_raises():
    with pytest.raises(TenantScopeError):
        TenantRepository(MagicMock(), "")


async def test_find_one_injects_user_id():
    repo, col = _repo("u1")
    await repo.find_one({"a": 1})
    assert col.find_one.call_args.args[0] == {"a": 1, "user_id": "u1"}


async def test_find_one_cannot_widen_scope():
    """Caller cố ghi user_id khác phải bị ghi đè bằng user của repo."""
    repo, col = _repo("u1")
    await repo.find_one({"user_id": "attacker"})
    assert col.find_one.call_args.args[0]["user_id"] == "u1"


async def test_insert_one_stamps_user_id():
    repo, col = _repo("u1")
    await repo.insert_one({"a": 1})
    assert col.insert_one.call_args.args[0]["user_id"] == "u1"


async def test_insert_many_stamps_all():
    repo, col = _repo("u1")
    await repo.insert_many([{"a": 1}, {"b": 2}])
    docs = col.insert_many.call_args.args[0]
    assert all(d["user_id"] == "u1" for d in docs)


async def test_update_one_upsert_sets_user_id_on_insert():
    repo, col = _repo("u1")
    await repo.update_one({"a": 1}, {"$set": {"b": 2}}, upsert=True)
    update = col.update_one.call_args.args[1]
    assert update["$setOnInsert"]["user_id"] == "u1"


async def test_count_is_scoped():
    repo, col = _repo("u1")
    await repo.count({"a": 1})
    assert col.count_documents.call_args.args[0]["user_id"] == "u1"


async def test_aggregate_prepends_match():
    repo, col = _repo("u1")
    await repo.aggregate([{"$group": {"_id": "$x"}}])
    pipeline = col.aggregate.call_args.args[0]
    assert pipeline[0] == {"$match": {"user_id": "u1"}}
