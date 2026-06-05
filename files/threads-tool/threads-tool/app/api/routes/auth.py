from datetime import datetime, timezone

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import CurrentUser, get_current_user
from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
)
from app.db.mongo import get_database
from app.models.user import Token, UserCreate, UserPublic

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
async def register(
    payload: UserCreate, db: AsyncIOMotorDatabase = Depends(get_database)
):
    if await db.users.find_one({"email": payload.email}):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email đã được đăng ký")
    doc = {
        "email": payload.email,
        "password_hash": hash_password(payload.password),
        "role": "user",
        "plan": "free",
        "created_at": datetime.now(timezone.utc),
    }
    res = await db.users.insert_one(doc)
    token = create_access_token(
        {"sub": str(res.inserted_id), "email": payload.email, "role": "user"}
    )
    return Token(access_token=token)


@router.post("/login", response_model=Token)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    # OAuth2PasswordRequestForm dùng field "username" — ta map sang email.
    user = await db.users.find_one({"email": form.username})
    if not user or not verify_password(form.password, user["password_hash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sai email hoặc mật khẩu")
    token = create_access_token(
        {"sub": str(user["_id"]), "email": user["email"], "role": user.get("role", "user")}
    )
    return Token(access_token=token)


@router.get("/me", response_model=UserPublic)
async def me(
    user: CurrentUser = Depends(get_current_user),
    db: AsyncIOMotorDatabase = Depends(get_database),
):
    doc = await db.users.find_one({"_id": ObjectId(user.user_id)})
    if not doc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Không tìm thấy user")
    return UserPublic(
        id=str(doc["_id"]),
        email=doc["email"],
        role=doc.get("role", "user"),
        plan=doc.get("plan", "free"),
        created_at=doc["created_at"],
    )
