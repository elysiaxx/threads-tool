# Trend Radar — Theo dõi nội dung public & phát hiện xu hướng

## 1. Định hướng (mục tiêu của module)

**Vấn đề:** người dùng cần biết *nội dung nào đang được đẩy lên xu hướng* trên Threads
để bắt trend, học cách viết, và canh thời điểm đăng. Threads có endpoint keyword
search chính thức nhưng bị rate-limit nặng và đòi scope `threads_keyword_search`
(phải qua Meta review). Vì vậy Trend Radar **không phụ thuộc OAuth**: nó dựa trên
`ThreadsPublicClient` (đọc Threads web công khai) để lấy bài + chỉ số engagement
(like / reply / quote / thời điểm đăng) của một **watchlist** các tài khoản mà
người dùng quan tâm (đối thủ, KOL, nguồn tin trong ngành).

**Mô hình "radar theo watchlist":**

```
tracked accounts (watchlist)        Celery Beat (định kỳ)
        │                                   │
        ▼                                   ▼
ThreadsPublicClient.list_user_posts  →  radar.collect_tracked
        │                                   │
        ▼                                   ▼
   public_posts (snapshot engagement, có lịch sử để tính velocity)
        │
        ▼
  chấm điểm xu hướng (score) theo NGƯỠNG cấu hình  →  /radar/posts, /radar/stats
```

Mỗi lần thu thập là một **snapshot**: ngoài chỉ số hiện tại còn lưu mốc trước đó để
tính **velocity** (tốc độ tăng tương tác / giờ) — yếu tố quan trọng để phân biệt
"đang lên" với "đã nguội".

## 2. Cách xác định "xu hướng" (có thể cấu hình)

Điểm xu hướng kết hợp **độ tương tác** với **độ mới** (decay theo thời gian, kiểu
Hacker News) để bài cũ dù nhiều like vẫn bị hạ bậc:

```
engagement = like + reply_weight·reply + quote_weight·quote
score      = engagement / (age_hours + 2) ^ gravity
velocity   = Δengagement / Δhours   (giữa 2 snapshot gần nhất)
```

Một bài được coi là **trending** khi vượt tất cả ngưỡng cấu hình. Tham số nằm trong
`trend_settings` (mỗi tenant một bản, sửa được từ UI):

| Tham số | Mặc định | Ý nghĩa |
|---|---|---|
| `min_likes` | 10 | Like tối thiểu để xét |
| `min_engagement` | 0 | Engagement tổng tối thiểu |
| `max_age_hours` | 48 | Chỉ xét bài mới trong N giờ |
| `reply_weight` | 2.0 | Trọng số reply trong engagement |
| `quote_weight` | 3.0 | Trọng số quote/repost |
| `gravity` | 1.5 | Tốc độ giảm điểm theo tuổi (cao = ưu tiên bài mới) |
| `min_score` | 0 | Điểm tối thiểu để lọt bảng xu hướng |
| `top_n` | 50 | Số bài giữ lại tối đa |

> Điểm và velocity được tính **lúc đọc** từ chỉ số đã lưu, nên đổi ngưỡng là bảng
> xếp hạng đổi ngay, không phải thu thập lại.

## 3. Thống kê trực quan (FE — trang "Xu hướng")

- **Thẻ tổng quan:** số bài theo dõi, số bài trending, số tài khoản nguồn, engagement TB.
- **Top tài khoản nguồn** (bar): tài khoản nào đang tạo nhiều nội dung trending.
- **Phân bố theo loại media** (bar): TEXT / IMAGE / VIDEO / CAROUSEL.
- **Dòng thời gian** (line): số bài trending theo ngày đăng.
- **Bảng xếp hạng**: bài trending kèm score, velocity, like/reply/quote, link.
- **Bảng điều khiển ngưỡng**: chỉnh `min_likes`, `max_age_hours`, gravity… và lưu.

## 4. Bảo mật & đa người dùng

- `public_posts` và `trend_settings` là collection theo tenant → truy cập **chỉ qua
  `TenantRepository`** (đóng dấu `user_id`). Index bắt đầu bằng `user_id`.
- Job thu thập nhận `user_id` và chỉ đọc tracked accounts của chính user đó.
- Đọc Threads public đi qua proxy pool của user (giảm rủi ro rate-limit / chặn IP).

## 5. API

| Method | Path | Vai trò |
|---|---|---|
| GET | `/api/radar/settings` | Lấy ngưỡng hiện tại |
| PUT | `/api/radar/settings` | Cập nhật ngưỡng |
| POST | `/api/radar/collect` | Thu thập ngay watchlist (enqueue Celery) |
| GET | `/api/radar/posts` | Danh sách bài trending (đã chấm điểm, lọc theo ngưỡng) |
| GET | `/api/radar/stats` | Số liệu tổng hợp cho biểu đồ |

Beat task `radar.dispatch_tracked` chạy mỗi 60 phút, fan-out `radar.collect_tracked`
theo từng user có tracked account.
