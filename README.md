# FraudLens — Chấm điểm rủi ro giao dịch có AI giải thích cảnh báo

Hệ thống web hoàn chỉnh cho bài toán **Fraud Analytics**: ingest giao dịch, tính feature hành vi, chấm điểm bằng **rule engine + ML**, đưa case vào **hàng chờ điều tra**, và dùng **AI tóm tắt vì sao bị gắn cờ** để analyst xác minh. Hệ thống **không bao giờ tự kết luận gian lận** — mọi kết luận do con người ghi nhận và lưu audit trail.

![Dashboard](docs/screenshots/dashboard.png)

## Tài khoản demo

| Vai trò | Email | Mật khẩu | Quyền |
|---|---|---|---|
| Quản trị | `admin@fraudlens.vn` | `Admin@12345` | Toàn quyền: user, rule, ngưỡng, audit, case |
| Chuyên viên | `analyst@fraudlens.vn` | `Analyst@123` | Điều tra case, nhập giao dịch, tạo giải thích, ghi kết luận |
| Chỉ xem | `viewer@fraudlens.vn` | `Viewer@123` | Chỉ đọc dashboard, giao dịch, case |

Dữ liệu demo (5.400+ giao dịch, 140+ case, 48 merchant) được sinh tự động ở lần khởi động đầu tiên. Tài khoản mật khẩu chỉ hiển thị trên UI khi `DEMO_MODE=true`.

## Điểm nổi bật

- **Dashboard vận hành**: dòng tiền, alert rate, hàng chờ theo P1/P2/P3, SLA quá hạn, độ chính xác cảnh báo, top ngành rủi ro, rule hit nhiều nhất.
- **Chấm điểm realtime**: mỗi giao dịch mới được tính feature (velocity 1h/24h, độ lệch chi tiêu, thiết bị mới, lệch quốc gia IP/thẻ, giờ đêm), chấm ML, cộng điểm rule, blend theo trọng số cấu hình.
- **Hàng chờ điều tra**: lọc/tìm kiếm, ưu tiên, SLA đếm ngược, nhận case, phân công, trạng thái, ghi chú.
- **Case detail**: điểm ML/rule, đóng góp tín hiệu, rule khớp, ngữ cảnh giao dịch, timeline, kết luận bắt buộc ghi chú + xác nhận.
- **AI explanation**: tóm tắt, tín hiệu chính, so sánh hành vi 30 ngày, câu hỏi xác minh, ghi chú nháp. Hỗ trợ OpenAI/Anthropic; **không có API key vẫn chạy** bằng template offline dựa trên dữ liệu thật.
- **Rule engine có UI**: bật/tắt, tạo/sửa rule với condition builder, trọng số, severity, thống kê hit.
- **Quản trị**: RBAC 3 vai trò, quản lý user, reset mật khẩu/thu hồi phiên, audit trail bất biến (before/after), cấu hình ngưỡng & trọng số, model card.
- **Production-ready**: Postgres, JWT + refresh token HTTP-only, rate-limit login, security headers, Docker, Render blueprint.

## Kiến trúc

```mermaid
flowchart LR
  UI[React SPA\nDashboard / Queue / Case] -->|JWT| API[FastAPI]
  API --> AUTH[Auth + RBAC]
  API --> ING[Ingest service]
  ING --> FEAT[Feature builder\n30d history]
  FEAT --> ML[Gradient Boosting]
  FEAT --> RULE[Rule engine]
  ML --> SCORE[Risk score]
  RULE --> SCORE
  SCORE --> CASE[Case + SLA + queue]
  CASE --> EXP[Explanation service]
  EXP -->|API key| LLM[OpenAI / Anthropic]
  EXP -->|fallback| TPL[Offline template]
  API --> DB[(PostgreSQL)]
  API --> AUDIT[Audit log]
```

Chi tiết pipeline và schema: [`docs/architecture.md`](docs/architecture.md).

## Công nghệ

| Lớp | Công nghệ |
|---|---|
| Backend | Python 3.13, FastAPI, SQLAlchemy 2, Pydantic v2 |
| Dữ liệu | PostgreSQL 14+ (mặc định, cả local lẫn production), SQLite (tuỳ chọn) |
| ML | scikit-learn HistGradientBoosting, joblib artifact, permutation importance |
| AI | OpenAI / Anthropic qua HTTP, fallback template offline |
| Frontend | React 19, TypeScript, Vite, Tailwind CSS, TanStack Query, Recharts |
| Hạ tầng | Docker multi-stage, docker-compose, Render Blueprint |

## Chạy local

### Cách nhanh (Windows)

```powershell
cd fraudlens
.\run.ps1
```

Script tự: tạo venv → cài dependency → **bật PostgreSQL local** → build frontend → chạy server.
Mở http://127.0.0.1:8000.

### Cơ sở dữ liệu

Ứng dụng dùng **PostgreSQL** cho mọi môi trường. Không cần cài Docker hay quyền admin:
`scripts/dev-db.ps1` tự khởi tạo một cluster riêng trong `.pgdata/`, lắng nghe
`127.0.0.1:5433`, user `postgres`, database `fraudlens` (trust auth — chỉ dùng cho máy cá nhân).

```powershell
.\scripts\dev-db.ps1 start     # bật cluster + tạo database nếu chưa có
.\scripts\dev-db.ps1 status    # kiểm tra server/database
.\scripts\dev-db.ps1 stop      # tắt cluster
.\scripts\dev-db.ps1 reset     # xoá sạch dữ liệu, lần chạy sau seed lại demo
```

Chuỗi kết nối mặc định: `postgresql+psycopg://postgres@127.0.0.1:5433/fraudlens`.
Đổi bằng biến môi trường `DATABASE_URL`, ví dụ:

```powershell
$env:DATABASE_URL = "postgresql+psycopg://user:pass@127.0.0.1:5432/fraudlens"
```

Muốn chạy nhanh bằng SQLite (không cần Postgres): `$env:DATABASE_URL = "sqlite:///./data/fraudlens.db"`.
Schema tạo bằng SQLAlchemy `create_all` ở lần khởi động đầu.

### Chạy tách backend/frontend để phát triển

```powershell
# Terminal 1
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
.\scripts\dev-db.ps1 start
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000

# Terminal 2
cd frontend
npm install
npm run dev
```

Frontend dev tại http://localhost:5173, proxy `/api` sang cổng 8000. API docs: http://127.0.0.1:8000/api/docs.

### Docker + PostgreSQL

```bash
docker compose up --build
```

Mở http://localhost:8000. Lần đầu container tự tạo schema và seed dữ liệu demo vào Postgres.

## Deploy online

Repo đã có `Dockerfile`, `docker-compose.yml` và `render.yaml`.

### Render (khuyến nghị, có URL công khai)

1. Push repo lên GitHub.
2. Vào Render → **New** → **Blueprint** → chọn repo.
3. Render đọc `render.yaml`, tạo Postgres + web service, tự sinh `JWT_SECRET`.
4. (Tuỳ chọn) nhập `OPENAI_API_KEY` trong Environment để bật LLM; bỏ trống vẫn chạy template offline.
5. Sau khi deploy, kiểm tra `https://<service>.onrender.com/api/health`.

Lưu ý free tier của Render sẽ ngủ sau thời gian rảnh; request đầu tiên có thể chậm 30–60 giây.

### Bất kỳ VPS / PaaS nào

```bash
docker build -t fraudlens .
docker run -p 8000:8000 \
  -e DATABASE_URL="postgresql://user:pass@host:5432/fraudlens" \
  -e JWT_SECRET="<chuoi-ngau-nhien-32-ky-tu>" \
  -e ENVIRONMENT=production \
  -e COOKIE_SECURE=true \
  -e DEMO_MODE=false \
  fraudlens
```

Biến môi trường đầy đủ: [`.env.example`](.env.example).

## Cấu hình AI

Mặc định hệ thống dùng **template offline** — nội dung vẫn dựa trên rule hit, đóng góp model và thống kê 30 ngày, không phải text giả. Để dùng LLM:

```env
OPENAI_API_KEY=sk-...
AI_MODEL=gpt-4o-mini
# hoặc
ANTHROPIC_API_KEY=...
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```

Prompt được giới hạn nghiêm ngặt: chỉ dùng dữ liệu giao dịch, không khẳng định gian lận, trả JSON có schema cố định. Nếu provider lỗi/timeout, hệ thống fallback offline và ghi rõ `offline-fallback`.

## Model & rule engine

- **13 feature**: log amount, giờ (sin/cos), đêm, lệch quốc gia, thiết bị mới, velocity 1h/24h, tỷ lệ chi tiêu, số merchant/24h, tuổi tài khoản, rủi ro ngành hàng, kênh online.
- **Model**: `HistGradientBoostingClassifier`, artifact đóng gói sẵn trong `app/ml/artifacts/`.
- **Ngưỡng mặc định**: cảnh báo ≥ 55, rủi ro rất cao ≥ 78; trọng số ML 55% / rule 45% — chỉnh được trong **Cài đặt** (admin).
- **Rule seed**: 8 rule (giá trị lớn, đêm, lệch địa lý, velocity, thiết bị mới, thử thẻ, ngành rủi ro, vượt thói quen). Rule hit được cộng điểm, cap 100.
- **Điểm cuối** = `ml_score × ml_weight + rule_score × rule_weight`, làm tròn 1 chữ số.

Model card đầy đủ: [`docs/model-card.md`](docs/model-card.md). Chỉ số hiện tại trên tập test tổng hợp: **AUC 0.9769**, precision 91.7%, recall 72.4%. Đây là benchmark trên dữ liệu mô phỏng, **không phải** cam kết hiệu năng trên dữ liệu ngân hàng thật.

Huấn luyện lại:

```powershell
.\.venv\Scripts\python -m app.ml.train --days 60 --customers 900
```

## Bảo mật & phân quyền

| Chức năng | Admin | Analyst | Viewer |
|---|:--:|:--:|:--:|
| Dashboard, giao dịch, case | ✅ | ✅ | ✅ (read) |
| Nhập / mô phỏng giao dịch | ✅ | ✅ | ❌ |
| Ghi chú, nhận case, kết luận | ✅ | ✅ | ❌ |
| Tạo giải thích AI | ✅ | ✅ | ❌ |
| Rule engine | ✅ | ❌ | ❌ |
| Người dùng | ✅ | ❌ | ❌ |
| Audit trail | ✅ | ❌ | ❌ |
| Sửa cấu hình/ngưỡng | ✅ | ❌ | ❌ |

- Access token JWT 45 phút; refresh token 7 ngày lưu hash trong DB, cookie `HttpOnly`, thu hồi khi logout/reset mật khẩu.
- Mật khẩu hash bằng `scrypt` (thuần stdlib), không lưu plaintext.
- Rate-limit đăng nhập sai (6 lần / 5 phút / email+IP).
- Audit log ghi actor, action, entity, before/after, IP, user-agent; không cho sửa qua API.
- Case đã có kết luận **không thể ghi đè**; đóng case bắt buộc có decision của analyst.
- Production: bật `COOKIE_SECURE=true`, `DEMO_MODE=false`, dùng `JWT_SECRET` ngẫu nhiên ≥ 32 ký tự.

## Kiểm thử

```powershell
# Mặc định: SQLite tạm (nhanh)
.\.venv\Scripts\python -m pytest -q

# Chạy đúng bộ test đó trên PostgreSQL (tạo sẵn database fraudlens_test)
.\.venv\Scripts\createdb.exe -h 127.0.0.1 -p 5433 -U postgres fraudlens_test   # lần đầu
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres@127.0.0.1:5433/fraudlens_test"
.\.venv\Scripts\python -m pytest -q

.\.venv\Scripts\ruff.exe check app tests
cd frontend; npm run build
```

`TEST_DATABASE_URL` khiến conftest drop & tạo lại schema, nên **chỉ trỏ vào database test riêng**.
CI (`.github/workflows/ci.yml`) chạy cả hai backend: PostgreSQL service + SQLite.

10 test API bao phủ: login/refresh, RBAC, ingest → case → audit, decision không thể ghi đè, AI offline explanation, note/timeline, rule CRUD, dashboard, simulator.

## API chính

| Method | Endpoint | Mô tả |
|---|---|---|
| POST | `/api/auth/login` · `/refresh` · `/logout` | Phiên đăng nhập |
| GET | `/api/dashboard?days=30` | Toàn bộ số liệu dashboard |
| GET | `/api/cases` · `/cases/{id}` | Hàng chờ & chi tiết case |
| PATCH | `/api/cases/{id}` | Gán người, đổi trạng thái/ưu tiên |
| POST | `/api/cases/{id}/decision` | Kết luận (bắt buộc note + confirm) |
| POST | `/api/cases/{id}/notes` · `/explain` | Ghi chú, tạo giải thích AI |
| GET/POST | `/api/transactions` | Danh sách, ingest & chấm điểm |
| POST | `/api/transactions/simulate` | Sinh giao dịch demo |
| GET/POST/PATCH/DELETE | `/api/rules` | Rule engine |
| GET/POST/PATCH | `/api/users` | Quản lý người dùng |
| GET | `/api/audit` | Audit trail |
| GET/PATCH | `/api/settings` | Ngưỡng & trọng số |
| GET | `/api/model/info` | Model card |
| GET | `/api/health` | Health check |

Swagger UI: `/api/docs`.

## Cấu trúc thư mục

```
fraudlens/
├── app/
│   ├── main.py            # FastAPI app, static SPA, health
│   ├── models.py          # SQLAlchemy models
│   ├── scoring.py         # ingest + feature + score + case
│   ├── rules.py           # rule evaluator
│   ├── explain.py         # AI/offline explanation
│   ├── seed.py            # dữ liệu demo
│   ├── ml/                # synthetic data, train, serve, artifacts
│   └── routers/           # auth, users, transactions, cases, rules, ...
├── frontend/src/
│   ├── pages/             # Dashboard, Queue, CaseDetail, ...
│   ├── components/        # AppShell, charts, badges, modal...
│   └── lib/               # api, auth, format, types
├── tests/
├── docs/
├── scripts/dev-db.ps1     # quản lý cluster PostgreSQL local (.pgdata, cổng 5433)
├── Dockerfile
├── docker-compose.yml
└── render.yaml
```

## Giới hạn & hướng phát triển

- Dữ liệu huấn luyện & demo là **tổng hợp**, không phải dữ liệu ngân hàng thật. Cần thẩm định lại model trên dữ liệu thực trước khi dùng production.
- Chưa có Alembic migration; schema tạo bằng `create_all` phù hợp demo. Production nên bổ sung migration.
- Rate-limit login lưu in-memory theo process; khi scale nhiều replica nên chuyển Redis.
- Có thể mở rộng: import CSV, webhook realtime, phân ca trực, báo cáo PDF, SSO, notification email/Slack.

## Ghi chú học thuật

Đề bài yêu cầu **không tự động kết luận gian lận khi chưa có người xác nhận**. FraudLens thể hiện rõ điều này ở 3 lớp: UI banner “chưa kết luận”, API chặn decision nếu thiếu `confirm` và ghi chú, và audit trail bất biến cho mọi kết luận. AI chỉ tạo **bản nháp giải thích** — không có quyền thay đổi trạng thái case.

Xem thêm: [`docs/spec-mapping.md`](docs/spec-mapping.md) — đối chiếu từng yêu cầu đề bài với phần đã triển khai,
và [`docs/compliance-audit.md`](docs/compliance-audit.md) — **kết quả kiểm chứng thực tế** (test, lint, build, thao tác UI, PostgreSQL) kèm danh sách việc còn thiếu.
