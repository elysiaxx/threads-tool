# Threads Tool Browser Helper

Chrome/Edge extension nội bộ để lấy Threads cookies, search `doc_id`, và mẫu GraphQL `variables` từ browser đã đăng nhập.

## Cài đặt

1. Mở `chrome://extensions` hoặc `edge://extensions`.
2. Bật `Developer mode`.
3. Chọn `Load unpacked`.
4. Chọn thư mục `browser-helper`.

## Sử dụng

1. Vào app `http://localhost:8080/radar`.
2. Copy app token trong panel `Phiên Threads`.
3. Mở extension `Threads Tool Helper`, dán token.
4. Bấm `Open Threads search`, đăng nhập Threads nếu cần.
5. Đợi trang search load vài giây, rồi bấm `Send cookies + doc_id to app`.

Extension không hiển thị giá trị cookie. Cookie được gửi về API local và lưu mã hoá như luồng cookie hiện tại. Mẫu `variables` giúp backend tái dùng đúng shape search request của Threads khi dò keyword/hashtag.
