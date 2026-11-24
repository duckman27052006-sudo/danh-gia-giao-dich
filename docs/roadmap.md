# Roadmap cải thiện FraudLens

> Tài liệu này tổng hợp kết quả audit ngày **24/11/2026** trên commit `9b4af7f`, mọi số liệu đều đo lại
> trong phiên audit đó. Dùng làm kế hoạch làm việc cho các đợt tiếp theo; mục nào đã xong được ghi rõ.
>
> Trạng thái nền: `pytest` (43 test) + `ruff` + `tsc --noEmit` + `vite build` đều sạch. Bundle production
> 82,8 KB gzip (entry) + 120,6 KB gzip (chunk biểu đồ). Đây không phải "sửa đồ án hỏng" mà là nâng từ
> demo hoàn chỉnh lên sản phẩm vận hành được.

## 0. Đã hoàn thành trong đợt này
### Nhóm A — lỗi thật (kèm test hồi quy)

| # | Lỗi | Sửa ở đâu | Test |
|---|---|---|---|
| A1 | Logout không xoá cookie refresh (header nằm trên `Response` bị bỏ) | `app/routers/auth.py` | `test_logout_clears_refresh_cookie` |
| A2 | Filter ngày lệch 7 giờ vì `.replace(tzinfo=None)` bỏ offset | `app/timeutils.py`, `app/routers/transactions.py`, `app/routers/audit.py` | `test_date_filter_uses_utc_not_wall_clock` |
| A3 | `PATCH /api/rules/{id}` với `conditions: []` → 500 do vi phạm CHECK | `app/schemas.py` | `test_patch_rule_with_empty_conditions_is_rejected` |
| A4 | `model_version` hard-code `gbdt-1.0.0` thay vì đọc artifact | `app/scoring.py`, `app/seed.py` | `test_model_version_comes_from_artifact` |
| A5 | `docker compose up` crash-loop (`production` + `COOKIE_SECURE=false`); production nhận DEMO_MODE mà không cần opt-in | `docker-compose.yml`, `app/config.py`, `app/main.py`, `render.yaml` | `test_production_requires_explicit_demo_opt_in` |
| A6 | `/api/health` trả `str(exc)` (lộ host/user/driver DB), không tách liveness/readiness | `app/main.py` | `test_health_is_liveness_and_ready_checks_dependencies` |
| A7 | Login prefill sẵn `admin@fraudlens.vn / Admin@12345`; bảng tài khoản demo hiện với cả viewer | `frontend/src/pages/Login.tsx`, `frontend/src/pages/Settings.tsx` | build production (nhánh `import.meta.env.DEV` bị loại) |

### Nhóm B — ML (thay đổi hành vi có đo lường)

| # | Thay đổi | Kết quả đo trên tập test |
|---|---|---|
| B1 | Hai ngưỡng thành phần: `risk = max(blend, ml nếu p≥0.65, rule nếu rule≥80)` | recall **0.473 → 0.675**, precision 0.987 → 0.919; 287 case được cứu thêm (227 fraud thật) |
| B2 | `contributions()` đổi từ `importance×z-score` sang **occlusion** (che từng feature về baseline) | top-1 trùng hiệu ứng thật 47,5% → đúng theo định nghĩa; sửa được 62/120 trường hợp báo ngược hướng |
| B3 | Script `scripts/eval_model.py` in PR-AUC, KS, Brier, bảng calibration, bảng ngưỡng, so sánh cơ chế gắn cờ | tái lập được AUC 0.9770 / PR-AUC 0.8965 / KS 0.8525 / Brier 0.0201 từ artifact |
| B4 | Model card viết lại bằng số đo thật + nêu rõ nhãn tổng hợp tương quan với feature | `docs/model-card.md` |
| B5 | `priority_for` suy ra từ ngưỡng cấu hình thay vì 85/68 hard-code | bỏ mâu thuẫn "critical nhưng P2" |

---

## 1. Ưu tiên P0 — nên làm trước khi bảo vệ / demo cho người khác

| Việc | Vì sao | Công sức | Tiêu chí xong |
|---|---|---|---|
| **Thu hồi access token** (`token_version` trên `users` + claim `tv` trong JWT) | Logout/reset mật khẩu hiện chỉ revoke refresh token; access token còn sống tới 45 phút | S (nửa ngày) | Test: reset mật khẩu → token cũ trả 401 |
| **Chống ghi đè kết luận** (optimistic locking: cột `version` + `If-Match`) | 2 analyst `POST /decision` đồng thời đều lọt qua `case.decision is None` → 2 kết luận trái nhau | S/M | Test song song 2 thread: đúng 1 thắng, cái sau 409 |
| **Đưa lời gọi LLM ra khỏi transaction DB** | `/cases/{id}/explain` giữ 1 connection (pool 5+10) suốt 25–45 s; ~15 request đồng thời là treo API | M | Đọc hết dữ liệu → `commit()`/`close()` → gọi HTTP → ghi kết quả |
| **`selectinload` + `GROUP BY` cho dashboard/case detail** | Đo được ~32 câu SQL/lần `GET /api/dashboard`, ~31 câu/trang queue 20 case | S/M | Dashboard ≤ 12 câu SQL, assert bằng `event.listen` |
| **CI GitHub Actions** (pytest + ruff + tsc + build) | README nói "CI chạy" nhưng repo không có workflow; 43 test đang chạy tay | S | Workflow xanh trên PR |

## 2. Ưu tiên P1 — nền tảng để vận hành được

| Việc | Vì sao | Công sức |
|---|---|---|
| **Alembic** thay `create_all` + `schema_migrations` chạy tay | Hiện `_ensure_foreign_keys` DROP mọi FK lạ trên cột, `create_all` không thêm cột mới cho bảng đã tồn tại → schema trôi âm thầm | M |
| **Observability**: request-id, log JSON, `/api/metrics`, đo p95 cho ingest/dashboard/explain | Hiện **0** metric/trace, không có cách nào biết chậm ở đâu | M |
| **Job queue cho AI** (bảng `jobs`: pending/done/failed + retry/backoff) | Bỏ hẳn gốc rễ cạn pool, không mất kết quả khi client timeout, có chỗ ghi token/cost | M/L |
| **Redis** cho rate-limit + lock | `_failures` hiện là dict RAM không giới hạn key, mỗi worker một bản | S |
| **Idempotency-Key** cho ingest | Retry không `external_id` hiện tạo bản ghi mới | S |
| **Cursor pagination** `(occurred_at, id)` + `pg_trgm` cho tìm kiếm | Offset + `COUNT(*)` mỗi trang và 5 `ILIKE '%q%'` sẽ chậm dần | M |
| **Test bổ sung**: 43 test / 36 endpoint, ~13 endpoint chưa có lời gọi nào; `conftest` `drop_all` một lần cho cả session | Chặng P0 sửa nhiều thứ nguy hiểm, cần lưới an toàn | M |
| **2FA/TOTP, password policy, self-service đổi mật khẩu** | Trước khi cho ai dùng thật | M |
| **Backup/restore runbook** (`pg_dump` định kỳ) | Render free không có backup | S |

## 3. Ưu tiên P2 — chất lượng model & nghiệp vụ

| Việc | Vì sao | Công sức |
|---|---|---|
| **Sửa `synthetic.py` để nhãn không leak feature**: sinh nhãn từ latent risk + noise, thêm fraud offline/soft, thêm hard negatives | Đây là phản biện dễ nhất khi bảo vệ: 95,1% fraud là online vs 55,4% legit; `channel_online` một mình cho AUC 0,699 | M |
| **Cold start**: `new_device=True` khi chưa có lịch sử, prior theo phân khúc, `amount_ratio` để trống thay vì =1 | Giao dịch đầu tiên 90 triệu hiện có p≈0.0103, rule "thiết bị mới" không bao giờ fire | S/M |
| **SHAP `TreeExplainer`** thay occlusion hoặc chạy song song để đối chiếu | Occlusion đúng hướng nhưng không additive chuẩn tắc; SHAP ~ms/dòng cho HGB | S/M |
| **Calibration + temporal CV + CI** (isotonic trên temporal holdout, TimeSeriesSplit, bootstrap CI) | Hiện chỉ có 1 con số điểm, không có khoảng tin cậy; permutation importance tính trên test | S/M |
| **Feedback loop**: dùng `cases.decision` để tính precision/recall thật, retrain, active learning quanh ngưỡng | Nhãn vàng đã có sẵn trong DB nhưng chưa dùng | M/L |
| **Drift monitoring** PSI/KS theo tuần, alert khi flagged-rate hoặc precision lệch | Model card đang tự nhận "chưa có giám sát drift" | M |
| **Hiệu chỉnh weight rule theo log-odds trên backtest** | Rule "đêm giá trị cao" có lift 1,19× (gần như không phân biệt) vẫn cộng 14 điểm; 8/8 rule dùng lại đúng feature của model → double counting | M |
| **Model registry / experiment tracking** (MLflow hoặc DVC) | Hiện artifact là file tĩnh, đổi model phải restart | M |

## 4. Ưu tiên P2 — tính năng nghiệp vụ

| Tính năng | Cho ai | Giá trị | Công sức |
|---|---|---|---|
| **Import CSV + bulk ingest** | tích hợp core banking | Lỗ hổng lớn nhất về "sản phẩm": hiện chỉ POST 1 giao dịch | M |
| **Export CSV + "Case report" PDF** (kèm audit lần export) | compliance | Bắt buộc khi điều tra thật; hiện phải copy tay từ bảng | S |
| **Realtime SSE** + toast "case vừa được người khác nhận" | analyst | Tránh 2 người nhận trùng case | M |
| **Bulk action + keyboard** (`j/k`, `r` nhận, `d` kết luận, `?` help) | analyst | Nhanh 2–3× so với click từng case | S/M |
| **SLA escalation job** + Slack/Telegram/email | supervisor | `sla_due_at` hiện chỉ để hiển thị | M |
| **Saved views + filter đồng bộ URL** | analyst | F5 không mất filter, share link được | S |
| **Command palette, dark mode, i18n vi/en** | toàn bộ | UX "sản phẩm thật"; dark mode cần chuyển màu sang CSS variables trước | S/M mỗi cái |

## 5. Đã audit nhưng **không** nên làm

- **Đừng đổi route `def` sang `async def`** khi vẫn dùng SQLAlchemy session đồng bộ. Hiện toàn bộ route là
  `def` nên DB/httpx chạy trong threadpool, event loop không bị chặn — đây là lựa chọn đúng.
- **Đừng thêm Alembic cùng lúc với migration idempotent** đang chạy: chọn một, nếu không hai cơ chế sẽ
  giẫm lên nhau. Lộ trình: viết baseline Alembic từ schema hiện tại → tắt `apply_schema_migrations`.
- **Đừng thay hai ngưỡng thành phần bằng "OR thô"** (flag nếu `p≥x` hoặc `rule≥y` mà không floor điểm):
  khi đó case có `risk_score` 40 nhưng vẫn gắn cờ, làm lệch risk band, màu score ring và thứ tự ưu tiên.
- **Đừng đổi theme Frutiger Aero rải rác trong từng trang**: theme đang tập trung ở `tailwind.config.js` +
  `index.css`, giữ kỷ luật đó.

## 6. Checklist trước khi nộp / demo

- [x] `pytest` xanh (43 test, PostgreSQL)
- [x] `ruff check app tests scripts` sạch
- [x] `tsc --noEmit` + `vite build` sạch
- [x] `docker compose up` không còn crash-loop
- [x] Model card khớp số đo thật (`scripts.eval_model`)
- [ ] Chạy thử luồng đầy đủ trên UI sau khi đổi ngưỡng (login → queue → case → decision → audit)
- [ ] Nếu deploy công khai: đặt `ALLOW_DEMO_IN_PRODUCTION=true` có chủ đích, hoặc `DEMO_MODE=false`
- [ ] Nếu nộp kèm báo cáo: dẫn lại bảng operating point trong `docs/model-card.md` (recall 0.473 → 0.675)

## 7. Cách kiểm chứng lại toàn bộ

```powershell
# 1. Test + lint backend
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\ruff.exe check app tests scripts

# 2. Đánh giá model + in bảng ngưỡng (cần PostgreSQL đang chạy)
.\.venv\Scripts\python.exe -m scripts.eval_model --with-rules

# 3. Đo tác động lên dữ liệu demo (chạy trên DB tạm fraudlens_test, KHÔNG đụng DB thật)
.\.venv\Scripts\python.exe -m scripts.measure_demo_seed

# 4. Frontend
cd frontend
npx tsc --noEmit
npm run build

# 5. Nâng cấp schema cho database đã có dữ liệu (thêm 2 cột ngưỡng)
cd ..
.\.venv\Scripts\python.exe .\scripts\migrate_db.py
```

## 8. Quyết định đã chốt: giữ nguyên artifact & dữ liệu demo

Đã cân nhắc việc viết lại `synthetic.py` để nhãn không còn tương quan trực tiếp với feature, rồi huấn
luyện lại. Quyết định: **không làm trong đợt này**, vì:

- Nó đổi artifact, toàn bộ số liệu trong model card/README, ảnh chụp màn hình và dữ liệu demo — trong khi
  **không** làm tăng khả năng đánh giá thật: dữ liệu vẫn là tổng hợp, nên mọi con số vẫn chỉ là benchmark
  pipeline, chỉ là thấp hơn và kém thuyết phục hơn.
- Đo thực tế: sinh lại demo bằng cơ chế mới cho ra 200 case với **187 case P1** (dataset quá dễ tách lớp),
  làm mất khả năng trình diễn phân loại P1/P2/P3 — tức là demo tệ hơn mà không trung thực hơn.

Việc **đúng** cần làm thay vào đó (đã ghi ở mục 3): tách bạch "benchmark pipeline" khỏi "năng lực phát
hiện", và cho `scripts/eval_model.py` chạy được trên dữ liệu gắn nhãn thật khi có — **đã làm**: dùng
`--csv` với 13 cột feature hoặc 12 cột context thô, hợp đồng cột ghi trong
[`model-card.md`](model-card.md#đánh-giá-trên-dữ-liệu-gắn-nhãn-thật), có test hồi quy ở
`tests/test_eval_dataset.py` (9 test: hai định dạng, cột nhãn tuỳ chỉnh, và 5 trường hợp dữ liệu bẩn bị
từ chối kèm số dòng).

Chừng nào chưa có nhãn thật, mọi con số chỉ nên đọc là *kiểm thử đường ống*, không phải hiệu năng model.

Viết lại `synthetic.py` chỉ đáng làm khi cần **kiểm thử hồi quy đường ống dưới model yếu** (ví dụ: đảm bảo
hệ thống không sập khi tín hiệu kém) — đó là mục đích test, không phải mục đích báo cáo.
