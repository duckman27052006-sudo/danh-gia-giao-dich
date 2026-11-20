# Security review & checklist deploy

Rà soát ngày **20/11/2026**, chuẩn bị cho việc đưa FraudLens lên Internet (web + PostgreSQL).

Phạm vi: xác thực, phân quyền, bảo vệ dữ liệu, cấu hình production, phụ thuộc bên ngoài (LLM),
và các lớp phòng thủ ở tầng HTTP.

## 1. Tổng kết

| Hạng mục | Trước audit | Sau audit |
|---|---|---|
| Cấu hình production sai (secret yếu, cookie không Secure) | Chỉ cảnh báo trong log | **Chặn khởi động** (fail-fast) |
| Swagger/OpenAPI lộ ở production | Luôn bật | Tự tắt ở production (`DOCS_ENABLED`) |
| Content-Security-Policy | Không có | Có (chỉ cho trang SPA, không ảnh hưởng Swagger) |
| HSTS | Không có | Bật ở production |
| Chống Host header injection | Không có | `ALLOWED_HOSTS` (TrustedHostMiddleware) |
| Giả IP qua `X-Forwarded-For` để né rate-limit | Tin cậy mù | Chỉ đọc khi `TRUST_PROXY_HEADERS=true` |
| Spam tạo lại giải thích AI | Không giới hạn | Cooldown 20 s/case (`EXPLAIN_COOLDOWN_SECONDS`) |
| Body request quá lớn | Không chặn | Chặn > 1 MB (413) |
| Gzip cho JSON/JS | Không | Có (`GZipMiddleware`) |
| Cache asset | Không | `immutable` 1 năm cho `/assets/*` |

## 2. Những gì đã có và đã kiểm tra lại

| Kiểm soát | Cách triển khai | Trạng thái |
|---|---|---|
| Hash mật khẩu | `scrypt` N=2^14, r=8, p=1, salt 16 byte (`app/security.py`) | Đạt |
| Access token | JWT HS256, hạn 45 phút, kiểm tra `type=access` | Đạt |
| Refresh token | Chuỗi ngẫu nhiên 48 byte, **chỉ lưu SHA-256** trong DB, xoay vòng mỗi lần refresh, thu hồi khi logout/reset | Đạt |
| Cookie | `HttpOnly`, `SameSite=Lax`, `Secure` theo cấu hình, `path=/api/auth` | Đạt |
| Phân quyền | RBAC ở dependency FastAPI (`admin`/`analyst`/`viewer`), chặn cả route UI lẫn API | Đạt |
| Rate-limit đăng nhập | 6 lần/5 phút theo `email+IP`, ghi audit `auth.login_failed` | Đạt |
| Audit trail | Chỉ có GET, không endpoint sửa/xoá; lưu actor, action, before/after, IP, UA | Đạt |
| Input validation | Pydantic v2, whitelist field/op cho rule engine | Đạt |
| SQL injection | Toàn bộ qua SQLAlchemy ORM, không nối chuỗi SQL | Đạt |
| Rò rỉ lỗi | 500 trả thông báo chung, stack chỉ vào log server | Đạt |
| Dữ liệu nhạy cảm | 100% dữ liệu demo tổng hợp, không PII thật | Đạt |
| Upload file | Không có endpoint upload | N/A |

## 3. Rủi ro còn lại (chấp nhận được cho đồ án, cần biết khi public)

| # | Rủi ro | Mức | Ghi chú / hướng xử lý |
|---|---|---|---|
| 1 | Access token lưu ở `localStorage` → nếu XSS thì mất token | Trung bình | Đã bật CSP chặn script ngoài; nếu cần chặt hơn: chuyển access token sang cookie HttpOnly + CSRF token |
| 2 | Tài khoản demo có mật khẩu công khai | **Cao nếu public** | Trước khi mở cho người ngoài: đổi mật khẩu 3 tài khoản, hoặc `DEMO_MODE=false` và tạo admin mới |
| 3 | Rate-limit lưu in-memory (mất khi restart, không chia sẻ giữa nhiều instance) | Thấp | 1 instance (Render free) thì ổn; scale thì chuyển Redis |
| 4 | Chưa có 2FA, chưa có chính sách mật khẩu mạnh | Thấp | Đồ án không yêu cầu; có thể thêm TOTP sau |
| 5 | Chưa có Alembic migration có version | Thấp | Đã có nâng cấp schema idempotent (`app/schema_migrations.py`); production nên chuyển sang Alembic |
| 6 | Chưa có backup tự động DB | Trung bình | Render Postgres có backup (gói trả phí) hoặc `pg_dump` định kỳ |
| 7 | Log/audit lưu IP + User-Agent | Thấp | Là dữ liệu cá nhân; chỉ admin đọc được, nên có thời hạn lưu trữ nếu dùng thật |
| 8 | Phụ thuộc OpenRouter (bên thứ ba) | Thấp | Prompt chỉ gửi dữ liệu giao dịch demo; lỗi/timeout tự fallback offline |

## 4. Biến môi trường bắt buộc khi deploy

```env
ENVIRONMENT=production
# Bắt buộc: chuỗi ngẫu nhiên >= 32 ký tự, KHÔNG dùng giá trị mặc định
JWT_SECRET=<chuoi-ngau-nhien-32-ky-tu>
COOKIE_SECURE=true
DATABASE_URL=postgresql://user:pass@host:5432/fraudlens

# Tên miền thật
CORS_ORIGINS=https://fraudlens.example.com
ALLOWED_HOSTS=fraudlens.example.com

# Render/Railway... chạy sau proxy → cần bật để rate-limit lấy đúng IP
TRUST_PROXY_HEADERS=true

# Dữ liệu demo
DEMO_MODE=false          # true = hiện mật khẩu demo trên trang login
SEED_ON_START=false      # true = tạo dữ liệu demo nếu database rỗng

# AI (chỉ model free)
OPENROUTER_API_KEY=sk-or-v1-...
AI_PROVIDER=openrouter
AI_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=openrouter/free
AI_FALLBACK_MODELS=baidu/ernie-5.5-flash-preview:free,nvidia/nemotron-3-ultra-550b-a55b:free
AI_TIMEOUT_SECONDS=75
```

Ứng dụng **từ chối khởi động** nếu `ENVIRONMENT=production` mà `JWT_SECRET` yếu/để mặc định,
`COOKIE_SECURE=false`, hoặc `CORS_ORIGINS` chứa `*`.

## 5. Checklist trước khi mở public

- [ ] `ENVIRONMENT=production`, `COOKIE_SECURE=true`, `JWT_SECRET` ngẫu nhiên ≥ 32 ký tự
- [ ] HTTPS hoạt động (Render/Railway tự cấp; VPS dùng Caddy/Nginx + Let's Encrypt)
- [ ] `ALLOWED_HOSTS` = đúng domain, `CORS_ORIGINS` = đúng domain
- [ ] `TRUST_PROXY_HEADERS=true` nếu chạy sau proxy
- [ ] **Đổi mật khẩu 3 tài khoản demo** hoặc set `DEMO_MODE=false` rồi tạo admin mới
- [ ] `SEED_ON_START=false` sau lần deploy đầu (tránh seed lại nếu DB bị xoá)
- [ ] Kiểm tra `GET /api/health` trả `database: postgresql`, `environment: production`
- [ ] Mở `/api/docs` → phải **404** (đã tắt ở production)
- [ ] Kiểm tra response có `Content-Security-Policy`, `Strict-Transport-Security`
- [ ] Bật backup database và biết cách restore
- [ ] Giới hạn quyền DB user (không dùng superuser)

## 6. Cách tự kiểm tra nhanh sau deploy

```bash
curl -sI https://<domain>/ | grep -Ei "content-security|strict-transport|x-frame|cache-control"
curl -s  https://<domain>/api/health
curl -s  https://<domain>/api/docs -o /dev/null -w "%{http_code}\n"   # phải là 404
# thử đăng nhập sai 7 lần → lần 7 phải trả 429
```
