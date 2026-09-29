# Template Alert và Runbook

Mỗi alert phải dựa trên triệu chứng người dùng hoặc SLO, không dựa trực tiếp vào tên implementation nội bộ.

## Alert 1

- Tên: `high_latency_p95`
- Severity: critical
- Duration: 5m
- Kênh thông báo: Slack `#day13-l3a-oncall`
- SLI/SLO liên quan: `primary_slo.fast_successful_requests` (`config/slo.yaml`) — good_event yêu cầu `latency_ms <= 3000`
- Điều kiện và thời gian duy trì: panel `latency` (`config/dashboard.yaml`) có `p95 > 3000ms`, duy trì liên tục ≥ 5 phút
- Ảnh hưởng tới người dùng: request `/chat` phản hồi chậm, trải nghiệm chờ lâu, có thể timeout ở client
- Ba bước kiểm tra đầu tiên:
  1. Mở `data/dashboard.html` (panel latency) xem P50/P95/P99 và TTFT hiện tại
  2. Mở Langfuse, tìm trace mới nhất theo `correlation_id` trong log có `latency_ms` cao — xem waterfall: chậm ở `retrieve-context` hay `llm-generate`
  3. Gọi `GET /health` xem field `incidents.rag_slow` — nếu `true`, đây là nguyên nhân giả lập retrieval chậm
- Mitigation tạm thời: nếu `rag_slow=true`, gọi `POST /incidents/rag_slow/disable`; nếu do LLM chậm thật, giảm tải bằng cách giảm concurrency load test hoặc scale thêm instance
- Owner: Ngô Đức Chung

## Alert 2

- Tên: `elevated_error_rate`
- Severity: critical
- Duration: 5m
- Kênh thông báo: Slack `#day13-l3a-oncall`
- SLI/SLO liên quan: `guardrails.error_rate_pct_max = 2` (`config/slo.yaml`)
- Điều kiện và thời gian duy trì: panel `errors` có `error_rate_pct > 2%`, duy trì liên tục ≥ 5 phút
- Ảnh hưởng tới người dùng: một phần request `/chat` trả HTTP 500, người dùng không nhận được câu trả lời
- Ba bước kiểm tra đầu tiên:
  1. Gọi `GET /metrics` xem `error_breakdown` — loại lỗi nào đang tăng (`RuntimeError`, ...)
  2. `grep '"event":"request_failed"' data/logs.jsonl` lấy `correlation_id` của các request lỗi gần nhất
  3. Dùng `correlation_id` đó tìm trace tương ứng trên Langfuse, xem span nào bị lỗi (thường là `retrieve-context` nếu `tool_fail`)
- Mitigation tạm thời: `GET /health` kiểm tra `incidents.tool_fail` — nếu `true`, gọi `POST /incidents/tool_fail/disable` để tắt giả lập lỗi vector store; nếu lỗi thật từ dependency ngoài, chuyển tạm sang fallback answer tĩnh
- Owner: Ngô Đức Chung

## Alert 3

- Tên: `cost_budget_spike`
- Severity: warning
- Duration: 10m
- Kênh thông báo: Slack `#day13-l3a-oncall`
- SLI/SLO liên quan: `guardrails.daily_cost_usd_max = 2.5` (`config/slo.yaml`), panel `cost` (`config/dashboard.yaml`)
- Điều kiện và thời gian duy trì: tổng `cost_usd` trong cửa sổ trượt 60 phút vượt $2.5, duy trì ≥ 10 phút (đủ lâu để loại trừ 1 request đột biến đơn lẻ)
- Ảnh hưởng tới người dùng: không ảnh hưởng trực tiếp trải nghiệm, nhưng cảnh báo sớm nguy cơ vượt ngân sách vận hành LLM
- Ba bước kiểm tra đầu tiên:
  1. Mở panel `tokens` trong `data/dashboard.html` — kiểm tra `tokens_out` có tăng đột biến không (nguyên nhân cost tăng thường do output token nhiều hơn bình thường)
  2. `GET /health` kiểm tra `incidents.cost_spike` — nếu `true`, `FakeLLM` đang giả lập output token x4
  3. Xem panel `quality` — nếu quality giảm mạnh cùng lúc, khả năng model đang trả lời dài dòng không cần thiết
- Mitigation tạm thời: nếu `cost_spike=true`, gọi `POST /incidents/cost_spike/disable`; nếu không, giới hạn `max_tokens` ở tầng gọi LLM hoặc tạm downgrade sang model rẻ hơn
- Owner: Ngô Đức Chung
