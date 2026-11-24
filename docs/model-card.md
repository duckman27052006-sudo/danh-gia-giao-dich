# Model card — FraudLens risk model

## Tổng quan

| Thuộc tính | Giá trị |
|---|---|
| Phiên bản | `gbdt-1.0.0` |
| Thuật toán | `HistGradientBoostingClassifier` (scikit-learn 1.9.1) |
| Bài toán | Binary classification: giao dịch gian lận / không gian lận |
| Số feature | 13 |
| Số mẫu | 72.768 giao dịch tổng hợp |
| Train / test | 80% / 20%, chia **theo thời gian** (time-based split, không shuffle) |
| Artifact | `app/ml/artifacts/model.joblib`, `metadata.json`, huấn luyện lại bằng `python -m app.ml.train` |

## Chỉ số trên tập test (14.554 dòng, 1.121 fraud ≈ 7,7%)

| Metric | Giá trị | Ghi chú |
|---|---|---|
| ROC-AUC | **0.9770** | tái lập từ artifact: 0.9769 trong metadata |
| PR-AUC (average precision) | **0.8965** | baseline ngẫu nhiên = 0.077 |
| KS | 0.8525 | khả năng tách lớp |
| Brier | 0.0201 | p dự báo trung bình 0.0756 vs fraud rate thật 0.0766 → calibration tốt |
| Precision / Recall @ p≥0.5 | 0.918 / 0.728 | operating point của **model**, không phải của hệ thống |

Bảng calibration (5 bin, đo trên tập test):

| Bin xác suất | Số dòng | p dự báo TB | Tỷ lệ fraud thật |
|---|---|---|---|
| 0.00–0.20 | 13.245 | 0.013 | 0.012 |
| 0.20–0.40 | 336 | 0.289 | 0.324 |
| 0.40–0.60 | 161 | 0.493 | 0.553 |
| 0.60–0.80 | 137 | 0.698 | 0.693 |
| 0.80–1.00 | 675 | 0.963 | 0.997 |

Model hơi *thiếu tự tin* ở nhóm xác suất cao (dự báo 0.963 trong khi thực tế 0.997) — chấp nhận được,
không làm mất hiệu lực của `predict_proba` để xếp hạng.

> Toàn bộ số liệu trên là benchmark trên **dữ liệu mô phỏng**, không đại diện cho hiệu năng trên dữ liệu
> ngân hàng thật. Tái lập bằng `python -m scripts.eval_model --with-rules`.

## Điểm cuối & cơ chế gắn cờ

Điểm rủi ro của một giao dịch:

```
blend      = ml_score × w_ml + rule_score × w_rule          (mặc định 0.55 / 0.45)
risk_score = max(blend, ml_score nếu p ≥ ml_flag_probability, rule_score nếu rule ≥ rule_flag_threshold)
gắn cờ     ⇔ risk_score ≥ review_threshold                   (mặc định 55)
```

Lý do của công thức `max`: với blend tuyến tính thuần và trọng số 55/45, **không tín hiệu nào một mình
đủ gắn cờ** — ML tối đa 55 điểm, rule tối đa 45 điểm, cả hai đều bằng hoặc dưới ngưỡng 55. Đo trên tập
test: recall của hệ thống chỉ **0.473** dù model đạt precision 0.987, tức là 591 giao dịch gian lận
không vào hàng chờ. Hai ngưỡng thành phần sửa đúng điểm này mà vẫn giữ một ngưỡng cảnh báo duy nhất.

Operating point đo trên tập test (8 rule seed đang bật):

| Cơ chế | Số case | Tỷ lệ gắn cờ | Precision | Recall | TP | FP | FN |
|---|---|---|---|---|---|---|---|
| Chỉ blend 55/45 (trước) | 537 | 3,7% | 0.987 | **0.473** | 530 | 7 | 591 |
| Hai ngưỡng OR (hiện tại: p≥0.65, rule≥80) | 824 | 5,7% | 0.919 | **0.675** | 757 | 67 | 364 |

→ Recall tăng **+20 điểm phần trăm** (0.473 → 0.675) với precision giảm từ 0.987 xuống 0.919; 287 case
được cứu thêm, trong đó 227 là gian lận thật và 60 báo nhầm (báo nhầm vẫn được analyst đóng bằng
`false_positive` nên sinh nhãn để cải thiện model).

Chọn ngưỡng: bảng dưới đo trên model thuần (chưa cộng rule gate), dùng để chọn `ml_flag_probability`.

| Ngưỡng p | Tỷ lệ gắn cờ | Precision | Recall | F1 | FPR |
|---|---|---|---|---|---|
| 0.30 | 7,7% | 0.816 | 0.813 | 0.815 | 1,53% |
| 0.40 | 6,7% | 0.881 | 0.764 | 0.819 | 0,86% |
| 0.50 | 6,1% | 0.918 | 0.728 | 0.812 | 0,54% |
| 0.60 | 5,6% | 0.946 | 0.685 | 0.795 | 0,33% |
| **0.65** | 5,3% | 0.958 | 0.663 | 0.783 | 0,25% |
| 0.70 | 5,1% | 0.976 | 0.642 | 0.775 | 0,13% |
| 0.80 | 4,6% | 0.997 | 0.600 | 0.749 | 0,01% |

Ngưỡng rule mặc định 80 là **lưới an toàn** chứ không phải kênh phát hiện chính: đo riêng (tắt cổng ML),
rule≥80 chỉ thêm 47 case cho 16 fraud thật. Hạ xuống 70 thì thêm 107 case nhưng chỉ 17 fraud — precision
của phần tăng thêm giảm mạnh, nên giữ 80.

## Feature

| Feature | Mô tả | Importance |
|---|---|---|
| `hour_sin`, `hour_cos` | Chu kỳ giờ trong ngày (UTC+7) | 39,1% (gộp) |
| `channel_online` | Giao dịch online | 24,3% |
| `category_risk` | Mức rủi ro ngành hàng | 12,6% |
| `velocity_1h` | Số giao dịch trong 1 giờ | 8,5% |
| `amount_log` | log(1 + số tiền) | 8,2% |
| `amount_ratio_log` | log(1 + amount / trung bình 30 ngày) | 4,1% |
| `country_mismatch` | Quốc gia IP ≠ quốc gia thẻ | 1,7% |
| `velocity_24h` | Số giao dịch trong 24 giờ | 1,0% |
| `new_device` | Thiết bị chưa từng thấy của khách hàng | 0,7% |
| `distinct_merchants_24d` | Số merchant khác nhau trong 24 giờ | ≈0 |
| `is_night` | 23h–5h | ≈0 |
| `account_age_days` | Tuổi tài khoản | **0,0** — xem cảnh báo bên dưới |

Permutation importance (3 vòng trên tập test). Vì importance tính trên test nên có thể lạc quan hơn
giá trị thật; khi cần con số chặt hơn hãy dùng cross-validation theo thời gian.

### Hai điểm lệch cần biết

1. **`account_age_days` là feature chết (importance 0).** Lúc huấn luyện, giá trị lấy từ
   `profile["signup_age"]` của dữ liệu tổng hợp; lúc serving, `app/scoring.py` tính từ giao dịch đầu
   tiên trong DB. Hai định nghĩa khác nhau (train/serve skew) và trong dataset tổng hợp `signup_age`
   gần như hằng số → model không học được gì. Muốn dùng feature này phải đồng bộ định nghĩa ở cả hai phía.
2. **Nhãn tổng hợp có tương quan trực tiếp với feature.** Mọi pattern fraud trong `app/ml/synthetic.py`
   bị ép `channel="online"`, IP thuộc {NG, RU, US, HK, ID}, 75% giao dịch ban đêm và ngành hàng thuộc
   {crypto, gift_card, gambling}. Đo được: 95,1% fraud là online so với 55,4% giao dịch hợp lệ; chỉ
   riêng `channel_online` đã cho AUC 0,699 và `velocity_1h` cho 0,749. **AUC 0,977 vì thế đo khả năng
   học lại luật sinh dữ liệu, không đo năng lực phát hiện gian lận thật.** Khi có dữ liệu thật phải
   đánh giá lại từ đầu; muốn dataset tổng hợp đáng tin hơn thì sinh nhãn từ một latent risk có nhiễu và
   thêm fraud ngoài các pattern trên (xem `docs/roadmap.md`).

## Đóng góp tín hiệu (attribution)

`app/ml/service.py::contributions` dùng **occlusion**: thay từng feature bằng giá trị trung bình của tập
huấn luyện rồi đo mức giảm xác suất fraud. Dấu của hiệu số cho biết feature đẩy rủi ro lên hay xuống.

- Cách cũ (`importance toàn cục × z-score`) không phụ thuộc model tại điểm đang xét: đo trên 120 mẫu,
  top-1 chỉ trùng hiệu ứng thật **47,5%** và **62/120 trường hợp báo ngược hướng**; mọi giao dịch đều
  được chuẩn hoá ~100% nên giao dịch điểm 12 vẫn hiện "Kênh online 35,7%".
- Occlusion đúng hướng theo định nghĩa nhưng **không** phải SHAP: không có tính additive chuẩn tắc và
  bỏ qua tương tác giữa các feature. Nếu cần attribution chuẩn để đối chiếu học thuật, thay bằng
  `shap.TreeExplainer` — chi phí ~ms/dòng cho HistGradientBoosting.

## Tác động lên dữ liệu demo (đo, không suy đoán)

Sinh lại dữ liệu demo bằng pipeline hiện tại (đo bằng `python -m scripts.measure_demo_seed` trên DB tạm):

| Chỉ số | Snapshot demo đang có | Nếu sinh lại |
|---|---|---|
| Giao dịch | 5.472 | 5.472 |
| Case | 142 | **200** |
| Alert rate | 2,6% | **3,65%** |
| Phân bố ưu tiên | P1/P2/P3 trải đều | **P1=187, P2=13, P3=0** |
| Risk band | — | critical 187, high 13, medium 16, low 5.256 |

Hai kết luận:

1. Cơ chế hai ngưỡng làm tăng số case ~41% trên chính dữ liệu demo — nhất quán với mức tăng recall đo
   trên tập test.
2. **Hàng chờ gần như toàn P1** vì dataset tổng hợp quá dễ tách lớp (AUC 0,977): giao dịch gian lận có
   xác suất 0,96–0,99 nên điểm cuối bị đẩy lên vùng `critical`. Đây là hệ quả của dữ liệu mô phỏng, không
   phải của logic ưu tiên — trên dữ liệu thật, phân bố điểm sẽ trải rộng hơn nhiều.

Vì vậy **không nên sinh lại dữ liệu demo chỉ để "cập nhật"**: nó làm demo khó đọc hơn (mất khả năng phân
biệt P1/P2/P3) mà không tăng tính đúng đắn. Snapshot hiện tại giữ nguyên như một ảnh chụp của phiên bản
trước; muốn xem cơ chế mới thì dùng nút **Mô phỏng giao dịch** hoặc `scripts/measure_demo_seed` trên DB tạm.

## Dữ liệu huấn luyện

- Sinh tổng hợp bằng `app/ml/synthetic.py`, seed cố định (42) để tái lập.
- Hành vi hợp lệ: chi tiêu theo ngành, giờ sinh hoạt, thiết bị quen, du lịch nước ngoài, mua sắm lớn.
- Gian lận mô phỏng 5 pattern: thử thẻ, chiếm đoạt tài khoản, lệch địa lý, bùng nổ velocity, ngành hàng rủi ro.
- 35–60% fraud event là “soft fraud” với tín hiệu yếu.
- Nhiễu hợp lệ: khách đi du lịch, đổi thiết bị, mua hàng giá trị lớn ban đêm.

> Lưu ý tái lập: `synthetic.py` dùng `datetime.now()` làm mốc kết thúc nên chạy lại có thể lệch 1 dòng
> (72.767 vs 72.768) và dịch nhẹ ranh giới train/test. Muốn bit-exact phải truyền mốc thời gian cố định.

## Cách sử dụng

- Model chỉ tạo **tín hiệu rủi ro**, không tự động block/kết luận.
- Kết hợp với rule engine theo trọng số cấu hình (mặc định 55/45) và hai ngưỡng thành phần.
- Analyst xem rule hit + đóng góp tín hiệu + so sánh hành vi trước khi quyết định.

## Hạn chế & rủi ro

1. **Dữ liệu tổng hợp + nhãn tương quan với feature**: AUC cao phần lớn phản ánh luật sinh dữ liệu, không
   phải năng lực phát hiện thật (xem mục cảnh báo ở trên). Đây là hạn chế lớn nhất của model card.
2. **Recall hệ thống 0.675** (sau khi thêm hai ngưỡng): vẫn còn ~1/3 gian lận lọt; rule engine và kiểm
   soát thủ công là lớp bổ sung, không có cơ chế nào tự block.
3. **Mất cân bằng**: fraud rate mô phỏng 7,7% cao hơn thực tế nhiều; precision trên production sẽ thấp hơn.
4. **Cold start**: khách chưa có lịch sử thì toàn bộ feature hành vi trung tính (`new_device=False`,
   `amount_ratio=1.0`); giao dịch đầu tiên 90 triệu vẫn có p≈0.01. Cần một prior theo phân khúc hoặc
   chặn review thủ công cho giao dịch đầu tiên giá trị lớn.
5. **Thiên lệch tiềm ẩn**: feature ngành hàng, quốc gia có thể ảnh hưởng không đồng đều giữa các nhóm
   khách hàng; cần kiểm định fairness trước khi triển khai.
6. **Không dùng cho quyết định tự động** hoặc chấm điểm tín dụng.
7. **Drift**: chưa có giám sát phân phối feature theo thời gian (PSI/KS) hay cảnh báo khi precision giảm.

## Tái lập & đánh giá

```powershell
# huấn luyện lại (ghi đè artifact)
.\.venv\Scripts\python -m app.ml.train --days 60 --customers 900

# đánh giá artifact hiện có + so sánh cơ chế gắn cờ (cần PostgreSQL có bảng rules)
.\.venv\Scripts\python -m scripts.eval_model --with-rules

# đo tác động lên dữ liệu demo (chạy trên DB tạm, không đụng DB thật)
.\.venv\Scripts\python -m scripts.measure_demo_seed
```

Metadata sau huấn luyện được ghi tại `app/ml/artifacts/metadata.json` và hiển thị trong trang **Cài đặt → Model card**.

## Đánh giá trên dữ liệu gắn nhãn thật

Khi có dữ liệu thật, **không cần sửa code** — dùng đúng script trên với `--csv`:

```powershell
.\.venv\Scripts\python -m scripts.eval_model --csv duong\dan\holdout.csv --label-column is_fraud
```

Hợp đồng của file CSV:

| Yêu cầu | Chi tiết |
|---|---|
| Cột nhãn | mặc định `label`, đổi bằng `--label-column`. Nhận `0/1`, `true/false`, `yes/no`, `fraud/legit` |
| Cách 1 — 13 cột feature | đủ `amount_log, hour_sin, hour_cos, is_night, country_mismatch, new_device, velocity_1h, velocity_24h, amount_ratio_log, distinct_merchants_24d, account_age_days, category_risk, channel_online` |
| Cách 2 — context thô | đủ `amount, hour, is_night, country_mismatch, new_device, velocity_1h, velocity_24h, amount_ratio, distinct_merchants_24d, account_age_days, merchant_category, channel` → script tự gọi `feature_vector` |
| Tính toàn vẹn | dòng lỗi (thiếu cột, nhãn lạ, không phải số) **bị báo kèm số dòng** và script thoát code 2; file chỉ có một lớp nhãn cũng bị từ chối vì không tính được AUC |

Output gồm đúng bộ chỉ số của model card: ROC-AUC, PR-AUC, KS, Brier, bảng calibration, và bảng
precision/recall/F1/FPR theo từng ngưỡng xác suất — dùng trực tiếp để chọn `ml_flag_probability`.

Lưu ý khi đọc kết quả trên dữ liệu thật:

- **Phải nêu rõ nguồn và mốc cắt thời gian** của tập holdout; đánh giá trên dữ liệu đã dùng để chỉnh
  feature/ngưỡng sẽ lạc quan.
- Nhãn lấy từ kết luận của analyst (`cases.decision`) có **thiên lệch chọn mẫu**: chỉ những case đã bị
  gắn cờ mới có nhãn, nên không đo được recall thật. Muốn đo recall cần một mẫu ngẫu nhiên giao dịch
  không bị gắn cờ, có người xác minh.
- Nếu PR-AUC trên dữ liệu thật thấp hơn 0.8965 nhiều thì đó là kết quả **bình thường và đáng tin hơn**
  con số tổng hợp; ghi lại vào bảng chỉ số phía trên thay vì giữ số cũ.
