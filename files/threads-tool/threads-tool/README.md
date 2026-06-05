# Threads Tool — Backend (FastAPI)

Khung dự án + nền tảng **Auth & Multi-tenancy** cho công cụ clone/phân tích Threads.
Giai đoạn này tập trung: xác thực, cách ly dữ liệu theo `user_id`, và bộ khung sẵn
sàng cho hai module tiếp theo là **Analytics** và **Collector**.

## Chạy nhanh (Docker)

```bash
cp .env.example .env
# sinh khóa mã hóa token rồi dán vào TOKEN_ENCRYPTION_KEY trong .env:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
docker compose up --build
```

- API:        http://localhost:8000  (Swagger: `/docs`)
- MinIO:      http://localhost:9001  (console; tạo bucket `media`, đặt public-read)
- Mongo:      localhost:27017 · Redis: localhost:6379

## Thử luồng auth

```bash
# đăng ký
curl -X POST localhost:8000/api/auth/register -H 'Content-Type: application/json' \
  -d '{"email":"a@b.com","password":"password123"}'
# đăng nhập (form, field tên là username = email)
curl -X POST localhost:8000/api/auth/login -d 'username=a@b.com&password=password123'
# gọi endpoint cần auth
curl localhost:8000/api/accounts -H "Authorization: Bearer <TOKEN>"
```

## Bản đồ file quan trọng

| File | Vai trò |
|---|---|
| `app/db/repository.py` | **TenantRepository** — ép `user_id` vào mọi đọc/ghi. Ranh giới cách ly dữ liệu. |
| `app/core/deps.py` | `get_current_user` (JWT) + `RepoFactory` gắn sẵn `user_id` cho request. |
| `app/core/security.py` | Hash mật khẩu, JWT, OAuth state token. |
| `app/core/crypto.py` | Mã hóa token Threads (Fernet). |
| `app/db/indexes.py` | Compound index bắt đầu bằng `user_id`; tạo `metrics_ts` time-series. |
| `app/services/oauth/` | OAuth pluggable: `base.py` (giao thức), `threads.py` (provider), registry. |
| `app/api/routes/accounts.py` | Kết nối tài khoản owned (OAuth) + theo dõi tài khoản tracked. |
| `app/services/storage.py` | Storage S3-compatible, prefix `media/{user_id}/...`. |
| `app/workers/` | Celery app + stub task (đều nhận `user_id`). |

## Quy ước cách ly dữ liệu (đọc trước khi viết code mới)

1. **Không thao tác trực tiếp collection thô** của user — luôn qua `TenantRepository`.
   Trong route: `repos = Depends(get_repos)` rồi `repos("posts")`, `repos("accounts")`...
2. Compound index mới phải **bắt đầu bằng `user_id`**.
3. Token mỗi user **riêng + mã hóa** (`access_token_enc`), không dùng chung.
4. Mọi Celery task **nhận `user_id`**; job poll lặp theo từng user active.

## Còn để lại (stub / TODO)

- `modules/collector`, `modules/analytics`: chưa triển khai.
- `services/oauth/threads.py`: tên endpoint/tham số theo luồng Meta đã tài liệu hóa —
  **đối chiếu lại docs hiện hành** trước khi chạy thật.
- Publish/Threads container: làm sau theo kế hoạch.
