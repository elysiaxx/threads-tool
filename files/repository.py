"""
Ranh giới cách ly dữ liệu giữa các user (multi-tenancy).

Mọi collection thuộc về user (accounts, sources, jobs, posts, searches, trends, ...)
PHẢI được truy cập qua TenantRepository, KHÔNG bao giờ thao tác trực tiếp lên
collection thô. Repository tự chèn `user_id` của user đang đăng nhập vào MỌI
filter (đọc) và MỌI document (ghi), nên code không thể vô tình đọc/ghi nhầm
dữ liệu của user khác — đây là lỗi rò rỉ phổ biến nhất của mô hình
"shared collection + user_id".
"""
from typing import Any, Mapping, Optional, Sequence

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorCollection


class TenantScopeError(RuntimeError):
    """Thao tác tenant-scoped mà thiếu user_id."""


class TenantRepository:
    def __init__(self, collection: AsyncIOMotorCollection, user_id: str):
        if not user_id:
            raise TenantScopeError("TenantRepository yêu cầu user_id không rỗng")
        self._col = collection
        self._user_id = user_id

    # --- nội bộ: ép phạm vi ---
    def _scoped(self, query: Optional[Mapping[str, Any]] = None) -> dict:
        q = dict(query or {})
        # Ghi đè cứng: caller không thể nới rộng phạm vi bằng user_id khác.
        q["user_id"] = self._user_id
        return q

    def _stamp(self, doc: Mapping[str, Any]) -> dict:
        d = dict(doc)
        d["user_id"] = self._user_id  # luôn đóng dấu chủ sở hữu khi ghi
        return d

    # --- đọc ---
    async def find_one(
        self,
        query: Optional[Mapping[str, Any]] = None,
        projection: Optional[Mapping[str, Any]] = None,
    ):
        return await self._col.find_one(self._scoped(query), projection)

    def find(
        self,
        query: Optional[Mapping[str, Any]] = None,
        projection: Optional[Mapping[str, Any]] = None,
        sort: Optional[Sequence] = None,
        skip: int = 0,
        limit: int = 0,
    ):
        cursor = self._col.find(self._scoped(query), projection)
        if sort:
            cursor = cursor.sort(sort)
        if skip:
            cursor = cursor.skip(skip)
        if limit:
            cursor = cursor.limit(limit)
        return cursor

    async def find_many(
        self,
        query: Optional[Mapping[str, Any]] = None,
        projection: Optional[Mapping[str, Any]] = None,
        sort: Optional[Sequence] = None,
        skip: int = 0,
        limit: int = 0,
    ) -> list:
        cursor = self.find(query, projection, sort, skip, limit)
        return await cursor.to_list(length=limit or None)

    async def count(self, query: Optional[Mapping[str, Any]] = None) -> int:
        return await self._col.count_documents(self._scoped(query))

    # --- ghi ---
    async def insert_one(self, doc: Mapping[str, Any]):
        res = await self._col.insert_one(self._stamp(doc))
        return res.inserted_id

    async def insert_many(self, docs: Sequence[Mapping[str, Any]]):
        res = await self._col.insert_many([self._stamp(d) for d in docs])
        return res.inserted_ids

    async def update_one(
        self,
        query: Mapping[str, Any],
        update: Mapping[str, Any],
        upsert: bool = False,
    ):
        if upsert:
            # Khi upsert tạo mới: đảm bảo document mới được đóng dấu user_id.
            update = dict(update)
            set_on_insert = dict(update.get("$setOnInsert", {}))
            set_on_insert["user_id"] = self._user_id
            update["$setOnInsert"] = set_on_insert
        return await self._col.update_one(self._scoped(query), update, upsert=upsert)

    async def update_many(self, query: Mapping[str, Any], update: Mapping[str, Any]):
        return await self._col.update_many(self._scoped(query), update)

    async def delete_one(self, query: Mapping[str, Any]):
        return await self._col.delete_one(self._scoped(query))

    async def delete_many(self, query: Mapping[str, Any]):
        return await self._col.delete_many(self._scoped(query))

    # --- aggregation ---
    async def aggregate(self, pipeline: Sequence[Mapping[str, Any]]) -> list:
        # Ép $match user_id làm stage ĐẦU TIÊN: không stage nào thấy dữ liệu
        # user khác (kể cả $lookup phía sau cũng chỉ join trong phạm vi đã lọc).
        scoped = [{"$match": {"user_id": self._user_id}}, *pipeline]
        return await self._col.aggregate(scoped).to_list(length=None)

    # --- tiện ích ---
    @staticmethod
    def oid(value: Any) -> ObjectId:
        return value if isinstance(value, ObjectId) else ObjectId(value)
