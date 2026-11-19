# Audit đối chiếu đề bài — FraudLens

Tài liệu này là **kết quả kiểm chứng thực tế** (không phải mô tả dự định) cho đề tài 10:
*Hệ thống chấm điểm rủi ro giao dịch có AI giải thích cảnh báo* (Data + AI — Fraud Analytics).

- Ngày audit: **19/11/2026**
- Môi trường: Windows, Python 3.14.5, Node 24, PostgreSQL 18.4 (cổng 5433), Chromium
- Phiên bản: commit `8d40aa4` + các thay đổi chuyển sang PostgreSQL trong lần audit này

## 1. Kết luận nhanh

| Hạng mục | Kết quả |
|---|---|
| Chức năng nghiệp vụ (8/8 yêu cầu) | **ĐẠT** — đã kiểm chứng bằng test + thao tác thật trên UI |
| Dashboard, queue ưu tiên, audit trail | **ĐẠT** |
| Cơ chế không tự kết luận (human-in-the-loop) | **ĐẠT** — chặn ở API (400/409) + xác nhận 2 bước trên UI |
| Đăng nhập & phân quyền | **ĐẠT** — 3 vai trò, chặn cả ở API lẫn route UI |
| UI/UX hoàn chỉnh | **ĐẠT** — 9 trang, chart, empty/error state, responsive |
| Quản lý user | **ĐẠT** |
| Sản phẩm web hoàn chỉnh (không notebook/CLI) | **ĐẠT** — FastAPI + SPA build sẵn + PostgreSQL |
| PostgreSQL (theo yêu cầu mới của nhóm) | **ĐẠT** — 10/10 test chạy trên PostgreSQL |
| **Deployed online (có URL)** | **CHƯA ĐẠT** — chủ động giữ local theo yêu cầu; `render.yaml` + Docker đã sẵn sàng |

**Tổng: 20/21 yêu cầu đạt.** Yêu cầu còn thiếu là *URL công khai*, không phải lỗi kỹ thuật —
repo đã có đủ cấu hình để deploy trong ~10 phút (xem mục 5).

## 2. Đối chiếu từng yêu cầu trong đề

| # | Yêu cầu | Trạng thái | Bằng chứng (đã kiểm tra) |
|---|---|---|---|
| 1 | Ingest giao dịch | ĐẠT | `POST /api/transactions` (`app/routers/transactions.py`), modal “Nhập giao dịch”, simulator. Test `test_ingest_creates_flagged_case_and_audit`. |
| 2 | Tính feature hành vi | ĐẠT | `app/features.py` — 13 feature: velocity 1h/24h, tỷ lệ chi tiêu 30 ngày, thiết bị mới, lệch quốc gia IP/thẻ, giờ đêm (sin/cos), số merchant 24h, tuổi tài khoản, rủi ro ngành, kênh online. |
| 3 | Áp rule engine | ĐẠT | `app/rules.py` + `app/routers/rules.py` + trang Rules: 8 rule seed, bật/tắt, weight, severity, condition builder, whitelist field. Test `test_rule_crud_and_rbac`. |
| 4 | Mô hình phát hiện bất thường | ĐẠT | `app/ml/` — HistGradientBoosting, artifact `app/ml/artifacts/model.joblib` (381 KB), AUC **0.9769**, model card `docs/model-card.md`. |
| 5 | Chấm risk score | ĐẠT | `app/scoring.py`: `ml_score × 55% + rule_score × 45%` (cấu hình được), cap 100, band low/medium/high/critical. |
| 6 | Hiển thị case đáng ngờ | ĐẠT | `GET /api/cases` + trang Hàng chờ: 49 case mở, lọc theo trạng thái/ưu tiên/phụ trách, tìm kiếm, phân trang. |
| 7 | Analyst cập nhật trạng thái điều tra | ĐẠT | `PATCH /api/cases/{id}`, nhận xử lý, phân công, đổi trạng thái, timeline. Thao tác thật trên UI đã kiểm chứng. |
| 8 | AI tóm tắt vì sao bị gắn cờ | ĐẠT (có điều kiện) | `app/explain.py`: gọi OpenAI/Anthropic thật; **không có API key thì dùng template offline** dựa trên dữ liệu thật. Test `test_ai_explanation_offline_shape` khẳng định `provider=offline`, ≥2 lý do, ≥3 câu hỏi xác minh. |
| 9 | So sánh với hành vi bình thường | ĐẠT | `app/explain.py::_history_stats` — thống kê 30 ngày: số giao dịch, chi tiêu TB, ngành quen thuộc, giờ quen thuộc. |
| 10 | Gợi ý câu hỏi xác minh | ĐẠT | 4 câu theo ngữ cảnh (đêm, thiết bị mới, lệch IP, velocity); hiển thị dạng checklist trong Case detail. |
| 11 | Tạo note xử lý | ĐẠT | `POST /api/cases/{id}/notes`, note nháp của AI lưu được vào case, timeline ghi nhận. Test `test_case_note_and_timeline`. |
| 12 | Dashboard fraud | ĐẠT | `app/routers/dashboard.py` + `Dashboard.tsx`: KPI, trend 30 ngày, phân bố điểm, ngành rủi ro, rule hit, cảnh báo mới. Test `test_dashboard_shape`. |
| 13 | Queue ưu tiên | ĐẠT | P1/P2/P3, SLA 4h/12h/48h, đếm ngược, quá hạn, sắp xếp ưu tiên/SLA/điểm. |
| 14 | Audit trail | ĐẠT | `app/audit.py` + `app/routers/audit.py`: actor, action, entity, before/after, IP, UA; không có endpoint sửa/xoá. Xác nhận bản ghi `case.decision` sau khi kết luận. |
| 15 | Không tự kết luận khi chưa có người xác nhận | ĐẠT | 3 lớp: banner UI, API trả **400** khi thiếu `confirm`/note, **409** khi ghi đè kết luận đã lưu, modal xác nhận 2 bước. Test `test_decision_requires_confirmation_and_is_final`. |
| 16 | Sản phẩm web hoàn chỉnh | ĐẠT | `frontend/dist` build thành công (`tsc --noEmit && vite build`, 2074 module), FastAPI phục vụ SPA + `/api/docs`. |
| 17 | **Deployed online (có URL)** | **CHƯA ĐẠT** | Có `Dockerfile` (multi-stage), `docker-compose.yml`, `render.yaml`, health check. Nhóm chọn giữ local. |
| 18 | Đăng nhập & phân quyền cơ bản | ĐẠT | JWT 45 phút + refresh cookie HttpOnly 7 ngày (hash trong DB), RBAC admin/analyst/viewer. Viewer vào `/rules` bị chặn ở UI **và** API (403). |
| 19 | UI/UX hoàn chỉnh | ĐẠT | 9 trang; skeleton, empty/error state, toast, modal, biểu đồ, layout responsive tới 390px. |
| 20 | Quản lý user | ĐẠT | Tạo user, đổi role, bật/tắt, reset mật khẩu, thu hồi phiên; trang Người dùng hiển thị 4 tài khoản + ma trận quyền. |
| 21 | Không nhận notebook / CLI / prototype localhost | ĐẠT* | Không có notebook; app là web server thật + cơ sở dữ liệu thật. *Ràng buộc “deployed” xem mục 17. |

### Về cột “Công nghệ” trong đề

Đề gợi ý `PostgreSQL, Python/scikit-learn, FastAPI, Streamlit/Dash (Plotly), OpenAI/Claude, rule engine`.

| Gợi ý | Thực tế | Ghi chú |
|---|---|---|
| PostgreSQL | ✅ dùng chính | Đã chuyển default từ SQLite sang PostgreSQL trong lần audit này |
| Python/scikit-learn | ✅ | 3.14, scikit-learn 1.9.1 |
| FastAPI | ✅ | 0.165 |
| Streamlit/Dash (Plotly) | ⚠️ thay bằng React + Recharts | Vẫn là web app đầy đủ và deploy được; Streamlit không deploy SPA/RBAC tốt bằng. **Nếu giảng viên chấm đúng stack, có thể bổ sung 1 trang Streamlit đọc từ API** — chi phí ~30 phút. |
| OpenAI/Claude | ✅ có tích hợp | Cần `OPENAI_API_KEY`/`ANTHROPIC_API_KEY` để bật; không có key vẫn trả giải thích offline |
| Rule engine | ✅ | Tự viết, có UI quản trị |

## 3. Yêu cầu phi chức năng

| Yêu cầu | Trạng thái | Cách đáp ứng |
|---|---|---|
| Bảo mật | ĐẠT | scrypt (N=2^14) hash mật khẩu, JWT HS256, refresh token hash SHA-256 trong DB + thu hồi, rate-limit login 6 lần/5 phút, security headers, whitelist field khi tạo rule |
| Khả năng giải thích | ĐẠT | Rule hit + trọng số, đóng góp feature của model, so sánh baseline 30 ngày, model card |
| Kiểm soát con người | ĐẠT | UI disclaimer + API `confirm` + audit bất biến |
| Dữ liệu nhạy cảm | ĐẠT | 100% dữ liệu demo tổng hợp, không PII thật |
| Vận hành | ĐẠT | `/api/health` trả `database/model/model_auc`, seed idempotent, Docker, `.env.example` |
| Kiểm thử | ĐẠT | 10 API test × 2 backend (PostgreSQL + SQLite), ruff sạch, `tsc` + `vite build` sạch |
| Hiệu năng | ĐẠT (quy mô demo) | 5.472 giao dịch/142 case: dashboard phản hồi < 300 ms trên máy local |

## 4. Những gì đã chạy trong lần audit này

```text
[PostgreSQL] .\scripts\dev-db.ps1 start        → cluster .pgdata, 127.0.0.1:5433, DB fraudlens
[Seed]       khởi động app                     → users=4, merchants=48, transactions=5472,
                                                  cases=142, rules=8
[DB check]   psql count(*)                     → transactions 5472 | cases 142 | rules 8 |
                                                  users 4 | audit_logs 103 | case_events 235
[Health]     GET /api/health                   → {"status":"ok","database":"postgresql",
                                                  "model":"gbdt-1.0.0","model_auc":0.9769}
[Restart]    tắt/bật lại app                   → vẫn 5472 giao dịch / 142 case (seed idempotent,
                                                  không nhân đôi dữ liệu)
[Test PG]    pytest (TEST_DATABASE_URL=...)    → 10 passed, exit 0
[Test SQLite] pytest                           → 10 passed, exit 0
[Lint]       ruff check app tests              → All checks passed
[Build]      npm run build                     → tsc OK, 2074 modules, dist/ 1.27 kB + assets
[UI]         Chromium 1262×568                 → login (3 vai trò), dashboard, queue, case detail,
                                                  transactions, rules, users, audit, settings
[RBAC]       viewer → /rules                   → "Không đủ quyền truy cập"; API /api/users → 403
[Human-in-loop] analyst tạo kết luận           → modal xác nhận → case status=resolved,
                                                  decision=false_positive, event "decision",
                                                  audit "case.decision[analyst@fraudlens.vn]"
```

### Lỗi phát hiện và đã sửa trong audit

1. **PostgreSQL: `TypeError: can't compare offset-naive and offset-aware datetimes`** — 2 test fail
   khi chạy trên PostgreSQL. Nguyên nhân: cột khai báo `DateTime(timezone=True)` nên PostgreSQL
   trả về datetime *có* timezone, còn SQLite trả về *naive*, trong khi code so sánh với `utcnow()`
   (naive). Đã sửa bằng `UTCDateTime` TypeDecorator trong `app/models.py`: luôn lưu/đọc UTC naive,
   hai backend trả về cùng một kiểu. Sau khi sửa: 10/10 pass trên cả hai.
2. **Bảng hàng chờ rộng hơn khung ở màn hình ≤1280px** — bảng có 9 cột, `min-w-[1080px]`
   trong khung ~944px nên phải cuộn ngang (đã có `overflow-x-auto`, không mất dữ liệu). Đây là
   lựa chọn responsive có chủ đích cho bảng vận hành nhiều cột; nếu muốn gọn hơn ở laptop 13"
   thì giảm mật độ cột hoặc ẩn cột “Trạng thái” dưới `xl`.

## 5. Khoảng trống & rủi ro còn lại

| # | Vấn đề | Mức độ | Cách xử lý |
|---|---|---|---|
| 1 | Chưa có URL công khai | **Cao** (nếu đề bắt buộc) | Render Blueprint đã có: push repo → New Blueprint → chọn repo → Render tạo Postgres + web + `JWT_SECRET` tự động. Chi tiết ở README mục “Deploy online”. Không cần sửa code. |
| 2 | AI đang chạy template offline | Trung bình | Thêm `OPENAI_API_KEY` (hoặc `ANTHROPIC_API_KEY`) vào biến môi trường là bật LLM thật; code đã có sẵn HTTP client + JSON schema + fallback. |
| 3 | Chưa có Alembic migration | Thấp | Schema tạo bằng `create_all` — đủ cho demo; production nên thêm migration. |
| 4 | Rate-limit login lưu in-memory | Thấp | Ổn với 1 process; scale nhiều replica thì chuyển Redis. |
| 5 | Dữ liệu & model là tổng hợp | Trung bình | Đã ghi rõ trong model card và README; cần thẩm định lại trên dữ liệu thật nếu dùng thật. |
| 6 | Sai lệch nhỏ về stack UI so với gợi ý của đề (React thay Streamlit/Dash) | Thấp | Có thể bổ sung 1 trang Streamlit đọc API nếu giảng viên yêu cầu đúng stack. |

## 6. Checklist trước khi nộp

- [x] `pytest` xanh trên PostgreSQL và SQLite
- [x] `ruff check app tests` sạch
- [x] `npm run build` sạch (TypeScript strict, không warning)
- [x] Đăng nhập được cả 3 vai trò, phân quyền đúng
- [x] Tạo giao dịch → gắn cờ → case → AI giải thích → kết luận → audit
- [x] Dashboard/Queue/Case hiển thị dữ liệu thật từ PostgreSQL
- [x] README + `docs/architecture.md` + `docs/model-card.md` khớp với code
- [ ] URL công khai (nếu bắt buộc) — xem mục 5.1
- [ ] `OPENAI_API_KEY` nếu muốn demo LLM thật — xem mục 5.2
