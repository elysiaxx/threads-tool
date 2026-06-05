# Tổng quan hệ thống: Công cụ Clone & Phân tích nội dung mạng xã hội

> Web-based tool · Backend Python (FastAPI) · MongoDB · Tích hợp Threads API chính thức

---

## 1. Mục tiêu & phạm vi

Một công cụ web với hai nhóm chức năng:

**A. Thu thập & đăng lại (Clone / Cross-post)**
- Tải nội dung: ảnh, video, story từ link nguồn.
- Đăng lên Threads (kiến trúc mở rộng được sang Instagram, Facebook, X...).
- Hỗ trợ đăng ngay hoặc lên lịch.

**B. Theo dõi & Phân tích (Analytics)**
- Đối tượng: tài khoản của bạn · đối thủ / tài khoản khác · hashtag / từ khóa / xu hướng.
- Phân tích: chỉ số tương tác · nội dung nào hiệu quả · thời điểm đăng tốt · xu hướng & sentiment.

---

## 2. Kiến trúc tổng thể

```
┌─────────────┐     HTTP/REST     ┌──────────────────┐
│  Web UI     │  ───────────────▶ │   API Layer      │
│  (React)    │                   │   (FastAPI)      │
└─────────────┘                   └────────┬─────────┘
                                           │
                 ┌─────────────────────────┼──────────────────────────┐
                 ▼                          ▼                          ▼
        ┌────────────────┐        ┌──────────────────┐        ┌────────────────┐
        │   MongoDB      │        │  Redis + Celery  │        │  Object Storage │
        │ (data + TS)    │        │  (queue/worker)  │        │ (S3/MinIO/R2)   │
        └────────────────┘        └────────┬─────────┘        └────────────────┘
                                           │
                          ┌────────────────┼────────────────┐
                          ▼                ▼                ▼
                   Threads API      Media download      NLP / Sentiment
                   (publish/read)   (yt-dlp, httpx)     (PhoBERT / LLM)
```

Celery xử lý mọi tác vụ nặng/dài (tải media, đẩy bài, poll metric định kỳ) để API luôn phản hồi nhanh.

---

## 3. Tech stack

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Backend | FastAPI (Python) | Async, hợp với I/O nặng |
| Database | MongoDB | Linh hoạt; có **time-series collection** cho metric |
| Queue / Worker | Celery + Redis | Tác vụ nền + lên lịch (Celery Beat) |
| Storage | MinIO / Cloudflare R2 / S3 | **Bắt buộc public URL** (xem mục 7) |
| Tải media | yt-dlp (video), httpx (ảnh) | Ổn định, đa nguồn |
| NLP | PhoBERT hoặc gọi LLM | Sentiment + phân loại chủ đề (tiếng Việt) |
| Frontend | React + Recharts/Chart.js | Dashboard biểu đồ |

---

## 4. Các module

### A. Collector (thu thập)
- Nhận link nguồn → tạo `Job`.
- Worker tải media → upload lên Object Storage → lấy public URL.
- Lưu metadata vào `sources`.

### B. Publisher (đăng bài)
- Threads API **không cho upload trực tiếp** → tạo media container từ public URL → publish container.
- Hỗ trợ đăng ngay hoặc lên lịch (Celery Beat).
- Quản lý token (auto-refresh mỗi <60 ngày).

### C. Analytics (phân tích)
- **Tài khoản của bạn:** lấy insights qua API (views, interactions, follower, demographics).
- **Đối thủ / hashtag / trend:** dùng keyword/hashtag search → lấy post công khai + engagement.
- **Scheduler poll định kỳ** (1–3h) → snapshot metric vào time-series.
- Tính toán phái sinh: "nội dung hiệu quả", "giờ đăng tốt" (tự tính, API không cho sẵn).

### D. NLP
- Phân loại sentiment (tích cực / trung tính / tiêu cực).
- Gắn nhãn chủ đề cho post để tổng hợp xu hướng.

---

## 5. Mô hình dữ liệu (MongoDB)

> **Mọi document đều gắn `user_id`** để phân tách dữ liệu theo người dùng (xem mục 6).

```
users:      { _id, email, password_hash, role, plan, created_at }

accounts:   { _id, user_id, type: "owned|tracked", platform, threads_user_id,
              username, access_token_enc?, token_expires_at? }   // token MÃ HÓA

sources:    { _id, user_id, original_url, platform, media_type,
              storage_url, status }                       // phần clone

jobs:       { _id, user_id, type: "publish|collect", source_id, account_id,
              status, scheduled_at, result, error }

posts:      { _id, user_id, account_id, thread_post_id, text, media_type,
              media_urls[], hashtags[], published_at,
              sentiment, topic }

metrics_ts: { ts, user_id, post_id, likes, replies, reposts, views }   // time-series

searches:   { _id, user_id, keyword|hashtag, last_run_at }

trends:     { _id, user_id, keyword, ts, volume, avg_engagement, sentiment }
```

> "Giờ đăng tốt" = group `posts` theo giờ/thứ, join engagement đỉnh trong `metrics_ts`, lấy trung bình.

**Index:** mọi compound index nên bắt đầu bằng `user_id`, ví dụ `posts {user_id: 1, published_at: -1}`.

---

## 6. Phân tách dữ liệu theo user (Multi-tenancy)

Mô hình: **shared collection + `user_id`** (chung DB, mỗi document gắn chủ sở hữu). Không tách DB riêng từng user trừ khi có yêu cầu compliance đặc biệt.

**Nguyên tắc cốt lõi:** mọi truy vấn **bắt buộc** filter theo `user_id` của người đang đăng nhập — đây là ranh giới cách ly dữ liệu.

4 điểm phải làm đúng (dễ gây rò rỉ dữ liệu giữa các user):

1. **Ép `user_id` ở tầng data access**, không tin frontend. Dùng một helper truy vấn tự chèn `user_id` — quên filter là lỗi rò rỉ phổ biến nhất.
2. **Compound index bắt đầu bằng `user_id`** — vừa nhanh vừa khớp pattern truy vấn.
3. **Token mỗi user là riêng và mã hóa** (`access_token_enc`). Mỗi user tự OAuth tài khoản Threads của họ; không dùng chung token. Cũng khớp với rate limit ~250 post/ngày tính theo từng tài khoản.
4. **Storage tách theo prefix** `media/{user_id}/...` — gọn khi xóa/đổi gói của một user.

Đồng bộ các phần khác:
- **Auth:** JWT → mỗi request giải mã ra `user_id`, gắn vào context.
- **Celery task:** mọi task nhận `user_id` làm tham số (lấy đúng token, ghi đúng chủ). Job poll định kỳ lặp **theo từng user** đang active.
- **Quota theo user:** giới hạn số tài khoản/keyword theo dõi mỗi user, tránh chiếm hết tài nguyên chung hoặc đụng trần app-level của Meta.

---

## 7. Luồng xử lý chính

**Clone & đăng**
1. User dán link → tạo `Job(collect)`.
2. Worker tải media → upload storage → public URL.
3. Tạo `Job(publish)` → Threads container → publish.
4. Lưu `posts`, cập nhật trạng thái job.

**Phân tích**
1. Đăng ký tài khoản/keyword cần theo dõi.
2. Celery Beat poll định kỳ → ghi `metrics_ts` / `trends`.
3. NLP gắn sentiment + topic.
4. API tổng hợp → dashboard biểu đồ.

---

## 8. Ràng buộc kỹ thuật then chốt (Threads API)

- **Media phải public:** API tự fetch từ URL bạn cung cấp, không upload trực tiếp → bắt buộc cloud storage có public URL.
- **Giới hạn đăng:** ~250 post / 24h / user (dùng chung pool Graph API).
- **Token:** hết hạn ~60 ngày → cần logic refresh.
- **App review:** cần Tech Provider Verification + review quyền `threads_content_publish` để chạy production.
- **Định dạng:** ảnh JPEG/PNG ≤ 8MB, rộng 320–1440px; video MP4/MOV ≤ 5 phút, ≤ 1GB; carousel tối đa 10 media.
- **Insights:** chỉ có dữ liệu từ 13/04/2024; demographics mở sau 100 follower.
- **Search:** rate limit chặt hơn nhiều endpoint khác → phải cache mạnh.
- **API không cho sẵn:** "best time to post" theo giờ, save/bookmark count, per-post link clicks → phải tự thu thập & tính.

---

## 9. Lưu ý pháp lý / vận hành

- Đảm bảo có quyền với nội dung đăng lại (nội dung của bạn, có license, hoặc được phép) và tôn trọng ToS từng nền tảng — để tránh khóa tài khoản/app.
- Ưu tiên dùng **API chính thức** thay vì scraping; tuân thủ rate limit để hệ thống bền vững.
- Tách biệt token/secret ra biến môi trường, không hardcode.

---

## 10. Roadmap đề xuất

1. **Auth + multi-tenancy nền tảng** — `users`, JWT, helper ép `user_id`. Làm trước vì cài sau rất khổ.
2. **Lấy insights tài khoản của bạn** — có data ngay để dựng dashboard.
3. **Scheduler poll + time-series + biểu đồ tương tác.**
4. **Tính "nội dung hiệu quả" + "giờ đăng tốt"** từ data đã có.
5. **Keyword/hashtag search** — theo dõi đối thủ & trend.
6. **Module clone + publish** (storage + Threads container).
7. **NLP sentiment** — sau cùng.
