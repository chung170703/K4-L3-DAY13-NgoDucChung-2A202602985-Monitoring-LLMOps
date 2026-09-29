# Báo cáo cá nhân — K4-L3A Day 13 Monitoring & LLMOps

> Mỗi học viên hoàn thiện một file duy nhất này. Khi dẫn evidence, dùng đường dẫn tương đối, ví dụ `evidence/07-trace-waterfall.png`.

## 1. Thông tin học viên

- **Họ và tên:** Ngô Đức Chung
- **MSSV:** 2A202602985
- **Lớp:** K4-L3A
- **Repository URL:** https://github.com/chung170703/K4-L3-DAY13-NgoDucChung-2A202602985-Monitoring-LLMOps
- **Commit SHA cuối:** `fb6f9df858903d1c52c741bfeb56e257991005f1`
- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1`
- **Tên project Langfuse cá nhân:** `day13-k4-l3a-2A202602985`

## 2. Evidence index

Điền đúng đường dẫn tới evidence thực tế. Có thể đổi tên hoặc dùng nhiều ảnh nếu cần.

| Evidence | Đường dẫn |
|---|---|
| Pytest cuối | `evidence/01-pytest.txt` |
| Log validator | `evidence/02-log-validator.txt` |
| Dashboard validator | `evidence/03-dashboard-validator.txt` |
| Structured log | `evidence/04-structured-log.txt` |
| PII redaction | `evidence/05-pii-redaction.txt` |
| Trace list | `evidence/06-trace-list.png` |
| Trace waterfall | `evidence/07-trace-waterfall.png` |
| Trace metadata | `evidence/08-trace-metadata.png` |
| Prompt versions | `evidence/09-prompt-versions.png` |
| Prompt rollback | `evidence/10-prompt-rollback.png` |
| Dashboard runtime | `evidence/11-dashboard-overview.png` |
| Incident metric | `evidence/12-incident-metric.png` |
| Incident log | `evidence/13-incident-log.txt` |
| Incident trace | `evidence/14-incident-trace.png` |

## 3. Kết quả kỹ thuật

| Nội dung | Baseline | Kết quả cuối | Nhận xét |
|---|---|---|---|
| `validate_logs.py` | 30/100 | 100/100 | CP1: middleware sinh/bind correlation_id, main.py enrich user_id_hash/session_id/feature/model/env, scrub_event đặt trước JsonlFileProcessor → PASSED cả 4 tiêu chí |
| `validate_dashboard.py` | 6/6 panel hợp lệ | 6/6 panel hợp lệ | Contract đã đạt sẵn từ starter; CP2 dựng thêm dashboard runtime thật (`scripts/render_dashboard.py` → `data/dashboard.html`) đọc đúng dữ liệu từ `data/logs.jsonl` |
| `pytest` | 22 passed | 24 passed | Thêm 2 test PII mới (`test_scrub_passport`, `test_scrub_vietnamese_address`) cho pattern bổ sung ở CP1 |
| Số traces hợp lệ | 1 root span / request (chưa có child) | ≥13 trace, mỗi trace 3 observation (root + 2 child) | CP2: `_retrieve` (as_type=retriever) và `_generate` (as_type=generation) tách thành child observation đúng quan hệ cha-con, xác nhận qua Langfuse API `v2/observations` |
| Số PII leak | 0 | 0 | Sau CP1: thêm pattern `passport`, `address_vn`; xác nhận log sạch PII bằng `validate_logs.py` (độc lập với `PII_PATTERNS` tự viết) |
| Latency P95 / TTFT P95 | Chưa đo | P95=4305ms, TTFT P95=55ms | Đo bằng `scripts/render_dashboard.py` panel latency (cửa sổ 60 phút, gồm cả dữ liệu incident CP3); P95 vượt threshold 3000ms do incident `rag_slow` |
| Retrieval success rate | | 100% | `tool_success_rate` panel errors — không có lần retrieval nào fail trong suốt quá trình test (kể cả lúc `rag_slow` bật, retrieval vẫn trả kết quả, chỉ chậm chứ không lỗi) |

## 4. Logging và PII

- **Cách tạo/nhận và truyền correlation ID:** `CorrelationIdMiddleware` (`app/middleware.py`) clear contextvars đầu mỗi request, lấy `x-request-id` từ header nếu client gửi kèm, nếu không tự sinh `req-<8-hex>` bằng `uuid.uuid4().hex[:8]`. Bind vào `structlog.contextvars` để mọi log trong request tự động có field này, đồng thời trả về qua response header `x-request-id` và `x-response-time-ms`.
- **Các metadata được ghi vào structured log:** `bind_contextvars(user_id_hash, session_id, feature, model, env)` trong `app/main.py` trước `log.info("request_received", ...)`. `user_id_hash` dùng SHA-256 cắt 12 ký tự (`hash_user_id`) để không log user_id thật.
- **Cách bảo đảm PII được scrub trước khi ghi:** processor `scrub_event` (dùng `scrub_text` từ `app/pii.py`) đặt trong danh sách `structlog.configure(processors=[...])` **trước** `JsonlFileProcessor()` — vì processor đó ghi file ngay lập tức, nên PII phải sạch trước bước đó chứ không phải chỉ trước bước render cuối. Pattern PII: email, phone_vn, cccd, credit_card (có sẵn) + thêm `passport`, `address_vn` (CP1).
- **Cách kiểm chứng kết quả:** `python scripts/validate_logs.py` — baseline 30/100 → sau CP1 đạt **100/100** (cả 4 tiêu chí PASSED). `pytest -q` 22 → 24 passed (thêm `test_scrub_passport`, `test_scrub_vietnamese_address`). Evidence: `evidence/02-log-validator.txt`, `04-structured-log.txt`, `05-pii-redaction.txt`.

## 5. Tracing và prompt versioning

- **Cách xác nhận traces do chính tôi tạo trong project cá nhân:** dùng chính `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY` của project `day13-k4-l3a-2A202602985`, gọi `GET /api/public/v2/observations` để xác nhận `projectId=cmumcfd0w1zjkad0d6kuqktzd` khớp project cá nhân trước khi tính là traces hợp lệ.
- **Cấu trúc root/retrieval/generation observations:** `LabAgent.run()` (root, `as_type="agent"`) gọi `self._retrieve()` (`as_type="retriever"`, tên `retrieve-context`) và `self._generate()` (`as_type="generation"`, tên `llm-generate`) — cả hai đều là method riêng có `@observe(...)`, tự động trở thành child của root nhờ OpenTelemetry context đang active. `capture_input=False, capture_output=False` ở cả 2 để tránh tự động chụp raw text (PII); input/output tự set thủ công bằng dữ liệu đã qua `summarize_text()` (đã scrub) hoặc chỉ số liệu tổng hợp (`doc_count`). `_generate` gọi `update_current_generation(model=self.model, usage_details={input,output,total}, cost_details={total}, prompt=managed_prompt)` để gắn đủ model/usage/cost/prompt-link.
- **Cách nối trace với log:** `correlation_id` (sinh ở middleware) được truyền vào `agent.run(correlation_id=...)` rồi gắn vào `metadata` của root span (`propagate_attributes(metadata={"correlation_id": ...})`) — cùng giá trị xuất hiện trong cả log JSONL và trace metadata, dùng để tra cứu chéo.
- **Prompt name:** `day13-chat`
- **Version/label baseline:** version 1, label `baseline` (đồng thời gán `production` ban đầu) — nội dung `Feature={{feature}}\nDocs={{docs}}\nQuestion={{message}}`
- **Version/label candidate:** version 2, label `candidate` — thêm dòng `Answer in at most 3 concise sentences.`
- **Trace ID của mỗi version:** correlation_id `req-promptv1demo` (label=baseline, trace field `version="1"`) và `req-promptv2demo` (label=candidate, trace field `version="2"`) — xác nhận qua `GET v2/observations`, field `version` của root span khớp đúng version prompt đã dùng.
- **Cách promote và rollback `production`:** dùng `PATCH /api/public/v2/prompts/day13-chat/versions/{version}` với `newLabels`. Promote: gán `["candidate","production"]` cho version 2 → chạy request `req-promoted-v2` xác nhận dùng v2. Rollback: gán `["baseline","production"]` cho version 1 → chạy request `req-rollback-v1` xác nhận dùng lại v1 (trạng thái cuối cùng để lại cho hệ thống).

## 6. Dashboard, SLO và alerts

- **Dashboard và sáu panel:** `scripts/render_dashboard.py` đọc `config/dashboard.yaml` + `data/logs.jsonl`, tính đúng 6 panel (latency P50/P95/P99+TTFT, traffic, error rate + retrieval success, cost, tokens, quality) và xuất ra `data/dashboard.html` — mỗi panel hiển thị time range 60 phút, đơn vị, và badge OK/BREACH so với threshold. Không dùng thêm dependency ngoài (Grafana/Streamlit) vì `validate_dashboard.py` xác nhận contract 6/6 đã đạt sẵn từ starter; công cụ tự viết đủ để chứng minh dashboard runtime dùng đúng dữ liệu.
- **SLO và lý do chọn:** giữ nguyên `primary_slo.fast_successful_requests` (`config/slo.yaml`) — good_event `latency_ms <= 3000`, target 99.5%/28 ngày — vì khớp đúng threshold panel `latency`; không siết chặt hơn (vd 99.9%) vì đây là dịch vụ demo nội bộ, không cần SLA production thật.
- **Cách tính error budget:** với target 99.5% và traffic ước tính ~500 request/ngày (~14.000 request/28 ngày) → error budget tuyệt đối = 14.000 × 0.5% = **70 request được phép chậm/lỗi** trong cả cửa sổ. Đối chiếu baseline thật: 1/22 `response_sent` vượt 3000ms (`req-promoted-v2`, 3344ms) → bad rate đo được ~4.5%, cao hơn nhiều so với 0.5% cho phép — minh hoạ rằng ở traffic thấp, 1 request chậm đã "đốt" đáng kể error budget minh hoạ (chi tiết trong `config/slo.yaml` note).
- **Ba alert và runbook tương ứng:** (`config/alert_rules.yaml` + `docs/alerts.md`)
  1. `high_latency_p95` (critical, 5m) — panel latency P95 > 3000ms → runbook: xem dashboard → soi trace waterfall theo correlation_id → kiểm tra `incidents.rag_slow`.
  2. `elevated_error_rate` (critical, 5m) — panel errors > 2% → runbook: `GET /metrics` error_breakdown → grep `request_failed` trong log lấy correlation_id → tìm trace lỗi → kiểm tra `incidents.tool_fail`.
  3. `cost_budget_spike` (warning, 10m) — tổng cost > $2.5/1h (theo `guardrails.daily_cost_usd_max`) → runbook: xem panel tokens có đột biến `tokens_out` không → kiểm tra `incidents.cost_spike`.

## 7. Điều tra challenge

- **Challenge ID:** `day13-k4-l3a-monitoring-llmops-v1` (cohort K4, incident cấu hình sẵn `rag_slow`, `latency_threshold_ms=2000`)
- **Khoảng thời gian điều tra:** 2026-09-29 09:04:52Z → 09:05:05Z (chạy `python scripts/inject_incident.py` rồi `python scripts/load_test.py --challenge --concurrency 5`)
- **Triệu chứng từ metrics:** `data/dashboard.html` panel latency **BREACH**. Quan trọng hơn: `load_test.py` in ra thời gian client thực nhận response là **10664ms → 13330ms** (tăng dần theo thứ tự request), vượt xa cả `latency_ms` server tự đo (~2660ms/request) lẫn ngưỡng `latency_threshold_ms=2000` của challenge.
- **Log line và correlation ID liên quan:** lọc `feature == "monitoring"` trong `data/logs.jsonl`, 5 request `req-5f5bde05, req-b678d161, req-2ef1e3fc, req-e07a8c63, req-7a6a6c94`, mỗi request có `latency_ms≈2660`. Mấu chốt: `request_received` của `req-b678d161` là `09:04:54.967940` — trùng khớp gần như tuyệt đối với `response_sent` của `req-5f5bde05` (`09:04:54.967079`) → server chỉ bắt đầu xử lý request #2 **sau khi** request #1 xử lý xong, dù `load_test.py` gửi cả 5 request cùng lúc (`--concurrency 5`).
- **Trace ID và span gây ảnh hưởng:** 5 trace tương ứng 5 session `k4-l3a-challenge-s01..s05` (vd trace `c5b4abe5ea81956b`, session `s01`). Mỗi trace: `retrieve-context ≈ 2.50s` (99%+ tổng thời gian) vs `llm-generate ≈ 0.16s` → retrieval là span chậm, khớp với `incident.rag_slow` trong `config/challenge.json`.
- **Root cause:** có **2 tầng nguyên nhân**:
  1. *Trực tiếp*: `incident.rag_slow=true` khiến `mock_rag.retrieve()` (`app/mock_rag.py`) `time.sleep(2.5)` mỗi lần gọi.
  2. *Sâu hơn (khuếch đại sự cố)*: endpoint `/chat` khai báo `async def` (`app/main.py`) nhưng gọi trực tiếp `agent.run()` — một hàm đồng bộ, blocking (chứa `time.sleep` bên trong retrieval) — mà **không offload sang thread pool**. Việc này chặn đứng event loop của FastAPI, nên 5 request gửi đồng thời bị xử lý **tuần tự**, khiến request cuối cùng phải chờ tới 13.3s thay vì chỉ ~2.6s nếu chạy song song thật sự.
  3. *Điểm mù observability phát hiện thêm*: `latency_ms` app tự ghi log chỉ đo từ lúc `agent.run()` bắt đầu chạy, không tính thời gian request bị "xếp hàng" chờ event loop rảnh — nên con số trong log/dashboard (2660ms) **thấp hơn nhiều** so với trải nghiệm thật của client (tới 13330ms).
- **Fix action:** đã `python scripts/inject_incident.py --disable` để tắt `rag_slow` ngay sau khi thu thập đủ evidence. Về lâu dài: bọc `agent.run()` bằng `starlette.concurrency.run_in_threadpool` (hoặc chuyển `retrieve()`/`generate()` thành async thật) để request không còn chặn event loop lẫn nhau.
- **Preventive measure:** (1) thêm phép đo "queue_wait_ms" (thời điểm request tới handler vs thời điểm `agent.run()` thực sự bắt đầu chạy) để không bỏ sót tầng nguyên nhân #3 trong tương lai; (2) chạy `load_test.py --concurrency > 1` định kỳ trong CI để phát hiện sớm vấn đề serialization; (3) alert `high_latency_p95` (đã có ở CP2, `config/alert_rules.yaml`) tiếp tục là tuyến phòng thủ đầu tiên khi P95 vượt ngưỡng.

## 8. Giải thích và tự đánh giá

- **Một quyết định kỹ thuật quan trọng và lý do:** Đặt processor `scrub_event` *trước* `JsonlFileProcessor()` trong `structlog.configure()` (thay vì đặt cuối cùng trước `JSONRenderer()` như nhiều người trực giác sẽ làm). Lý do: `JsonlFileProcessor()` ghi file ngay lập tức khi pipeline chạy tới nó, nên nếu scrub đứng sau, PII đã kịp ghi ra đĩa trước khi bị redact — sửa sau không còn ý nghĩa. Quyết định này cho thấy thứ tự processor trong logging pipeline quan trọng ngang với bản thân logic scrub.
- **Một lỗi/blocker đã gặp:** Khi demo prompt versioning, script gọi `client.get_prompt()`/`client.create_prompt()` qua Langfuse SDK liên tục bị `httpx.ReadTimeout`, dù `curl` gọi thẳng REST API cùng endpoint lại chạy được trong ~2 giây.
- **Cách tìm nguyên nhân và xử lý:** So sánh curl (thành công) với SDK (timeout) để cô lập vấn đề — xác định do `resolve_prompt()` trong code gọi `get_prompt(..., fetch_timeout_seconds=2, max_retries=0)`, quá ngắn cho một kết nối TLS "nguội" (cold connection) khi chạy script standalone lần đầu. Xử lý bằng cách "warmup" — gọi thử một request với timeout dài hơn trước, để connection pool đã sẵn sàng khi code thật chạy với timeout ngắn.
- **Cách hiểu luồng Metrics → Logs → Traces:** Qua CP3 mới thấy rõ 3 tầng bổ trợ nhau chứ không thay thế nhau: metric (dashboard) chỉ cho biết "có vấn đề" (panel latency BREACH) nhưng không biết request nào; log cho biết chính xác request nào bị ảnh hưởng (`correlation_id`) và thời điểm; trace cho biết *bên trong* request đó, bước nào (span) gây chậm. Thiếu 1 trong 3 là không đủ để kết luận root cause chắc chắn — đúng như bài đã nhấn mạnh "ba bằng chứng phải cùng chỉ về một nguyên nhân".
- **Vai trò của prompt version, token/cost, SLO hoặc rollback trong vận hành LLM:** Prompt version + rollback giúp thay đổi hành vi hệ thống (nội dung câu trả lời) mà không cần deploy lại code — nhưng đổi lại, phải theo dõi được version nào đang chạy tại mỗi thời điểm (qua trace metadata) để không bị "mất dấu" khi có sự cố. SLO/error budget biến latency từ một con số mơ hồ thành một ngân sách cụ thể có thể "tiêu" và "cạn" — giúp quyết định khi nào cần alert thay vì chỉ nhìn số liệu cảm tính.
- **Điều quan trọng nhất đã học:** Một hệ thống có thể "trông ổn" ở metric nội bộ (log ghi `latency_ms≈2660ms` mỗi request) nhưng trải nghiệm người dùng thực tế lại tệ hơn nhiều (chờ tới 13.3s) — nếu metric đo sai chỗ (không tính thời gian xếp hàng chờ xử lý), nó tạo ra "điểm mù" khiến sự cố nghiêm trọng hơn con số báo cáo. Bài học: luôn tự hỏi "con số này đo từ đâu đến đâu" trước khi tin vào nó.
- **Hạn chế hoặc phần chưa hoàn thành, nếu có:** Dashboard tự viết (`scripts/render_dashboard.py`) là công cụ tĩnh (chạy 1 lần ra file HTML), không tự động refresh theo `refresh_seconds` như dashboard thật (Grafana). Ngoài ra, root cause tầng 2 (event loop bị block) phát hiện được nhưng chưa fix trong code (`agent.run()` vẫn chưa được đưa vào `run_in_threadpool`) — nếu có thời gian, đây là việc nên làm tiếp.

## 9. Checklist trước khi nộp

- [x] Kết quả và evidence thuộc commit SHA cuối.
- [x] Tất cả ảnh/output mở được bằng đường dẫn tương đối.
- [x] Incident evidence nối đúng metric → log → trace.
- [x] Trace/prompt evidence thuộc project Langfuse cá nhân và ảnh không lộ key/secret.
- [x] Repository chạy lại được theo README.
- [x] Không có secret, API key, PII thô hoặc evidence của người khác/lớp khác.
- [ ] URL repo và commit SHA cuối đã được nộp trên LMS/Codelabs. *(chưa nộp — xem ghi chú bên dưới)*
