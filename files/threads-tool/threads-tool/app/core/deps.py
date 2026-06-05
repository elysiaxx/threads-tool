"""
Dependency injection cho auth + multi-tenancy.

Luồng: JWT -> get_current_user -> user_id trong context -> get_repos trả về
RepoFactory đã gắn user_id. Route lấy repo qua factory:

    @router.get("")
    async def list_accounts(repos: RepoFactory = Depends(get_repos)):
        accounts = repos("accounts")     # TenantRepository đã scoped theo user
        return await accounts.find_many()
"""
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import decode_access_token
from app.db.mongo import get_database
from app.db.repository import TenantRepository

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


class CurrentUser:
    def __init__(self, user_id: str, email: str, role: str):
        self.user_id = user_id
        self.email = email
        self.role = role


async def get_current_user(token: str = Depends(oauth2_scheme)) -> CurrentUser:
    payload = decode_access_token(token)
    if not payload or "sub" not in payload or payload.get("typ") == "oauth_state":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token không hợp lệ hoặc đã hết hạn",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return CurrentUser(
        user_id=payload["sub"],
        email=payload.get("email", ""),
        role=payload.get("role", "user"),
    )


class RepoFactory:
    """Tạo TenantRepository đã gắn sẵn user_id của request hiện tại."""

    def __init__(self, db: AsyncIOMotorDatabase, user_id: str):
        self._db = db
        self._user_id = user_id

    @property
    def user_id(self) -> str:
        """user_id của request hiện tại (để truyền vào Celery task)."""
        return self._user_id

    def __call__(self, collection_name: str) -> TenantRepository:
        return TenantRepository(self._db[collection_name], self._user_id)


def get_repos(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
) -> RepoFactory:
    return RepoFactory(db, user.user_id)
