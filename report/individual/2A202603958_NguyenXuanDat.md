# Báo cáo cá nhân — Day 6: Data Ingestion Engineering

- **Họ và tên:** Nguyễn Xuân Đạt
- **Mã học viên (MSSV):** `2A202603958`
- **Lớp / Nhóm:** `L3B`

---

## 1. Dữ liệu và pipeline

### Chủ đề, nguồn/quyền, số trang và quy tắc tính trang
- **Tài liệu sử dụng:** *Sổ tay Tân sinh viên Trường Đại học FPT năm 2026* (`document_id`: `fptu_so_tay_tsv_2026`), lưu tại [`data/2026_So-tay-TSV_compressed.pdf`](../../data/2026_So-tay-TSV_compressed.pdf) (bản sao thực thi tại [`starter/data/2026_So-tay-TSV_compressed.pdf`](../../starter/data/2026_So-tay-TSV_compressed.pdf)).
- **Chủ đề:** Quy chế đào tạo đại học hệ chính quy, nội quy sinh viên, quy định tài chính – học phí, khảo thí, thư viện, dịch vụ công nghệ thông tin (IT), đời sống sinh viên và công tác phát triển cá nhân (PDP) tại Trường Đại học FPT.
- **Nguồn và quyền sử dụng:** Tài liệu hướng dẫn học vụ công khai do Trường Đại học FPT phát hành cho sinh viên khóa mới; được phép sử dụng cho mục đích học tập, nghiên cứu và thực hành kỹ thuật trong phạm vi môn học. Chi tiết khai báo tại [`data/manifest.json`](../../data/manifest.json).
- **Thống kê số trang và quy tắc tính trang hợp lệ:**
  - **Tổng số trang vật lý trong file PDF:** `112` trang (đánh số từ `1` đến `112`).
  - **Số trang nội dung hợp lệ đưa vào nạp (ingested valid content pages):** `94` trang (vượt mức tối thiểu `>= 30` trang nội dung hợp lệ theo yêu cầu bài lab), tổng cộng **`101.194` ký tự** sau chuẩn hóa (trung bình `1.076,5` ký tự/trang hợp lệ).
  - **Số trang bị loại trừ:** `18` trang, bao gồm:
    1. `4` trang bìa và trang ảnh đồ họa không chứa văn bản (`trang 1, 2, 111, 112`).
    2. `2` trang lời ngỏ / thông điệp đầu sách có mật độ chữ thấp (`trang 3, 6`).
    3. `2` trang Mục lục (`trang 4, 5`) chỉ chứa danh sách tên mục và số trang dễ gây nhiễu truy xuất.
    4. `10` trang bìa ngăn cách chương (`trang 7, 13, 19, 31, 40, 54, 58, 66, 85, 109`) chỉ chứa số thứ tự chương và tiêu đề lớn (< 80 ký tự).
  - **Quy tắc tính trang hợp lệ (được cài đặt tự động trong [`starter/src/ingestion.py`](../../starter/src/ingestion.py)):** Một trang được tính là trang nội dung hợp lệ khi và chỉ khi: (1) không thuộc tập trang bìa, mục lục hoặc bìa ngăn chương, và (2) sau khi chuẩn hóa văn bản có độ dài tối thiểu `>= 120` ký tự và `>= 20` từ. Số trang gốc (`page`) luôn được bảo toàn theo đúng số thứ tự trang vật lý của PDF (`1..112`) để đối chiếu nguồn chính xác.

### Chuẩn hóa, lỗi và giới hạn
- **Quy trình chuẩn hóa văn bản (`normalize_text` trong [`starter/src/ingestion.py`](../../starter/src/ingestion.py)):**
  1. Đọc từng trang PDF bằng thư viện `pypdf==7.0.0`.
  2. Chuẩn hóa bảng mã tiếng Việt về dạng **Unicode dựng sẵn (`NFC`)** để tránh lỗi lệch dấu thanh khi so khớp chuỗi hoặc tạo embedding.
  3. Loại bỏ các ký tự điều khiển ẩn và ký tự ngắt từ mềm (`\x00`, `\ufeff`, `\u200b`, `\xad`), chuẩn hóa toàn bộ dấu xuống dòng `\r\n` và `\r` về `\n`.
  4. Lọc bỏ các dòng chỉ chứa số trang đơn lẻ ở đầu hoặc cuối trang (header/footer).
  5. Nối các dòng bị ngắt giữa câu do khổ dàn trang PDF thành đoạn văn liền mạch, nhưng **bảo toàn ranh giới ngắt đoạn (`\n\n`)** trước các đề mục đánh số (`I.`, `II.`, `1.`, `2.`, `1.1`, `a.`, `b.`) và các dòng liệt kê (`•`, `-`, `+`).
- **Lỗi và giới hạn khi trích xuất PDF:**
  - Một số trang trong Sổ tay được thiết kế dưới dạng **bố cục 2 cột** hoặc **bảng biểu / sơ đồ khối** (ví dụ: trang 10 về chuẩn đầu ra khối ngành, trang 17–18 về khung xử lý kỷ luật, trang 86–90 về danh sách câu lạc bộ). Khi trích xuất bằng `pypdf`, thứ tự luồng văn bản đôi khi đọc các ô tiêu đề cột liên tiếp trước rồi mới đọc tới phần nội dung chi tiết bên dưới. Hiện tượng này không làm mất chữ nhưng làm giảm nhẹ tính mạch lạc tự nhiên ở các trang có bảng phức tạp.

### Embedding model/provider/version/số chiều, vector store/version, metric, lệnh chạy và chi phí
- **Embedding model:**
  - **Tên model:** `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
  - **Provider & thư viện:** HuggingFace / `sentence-transformers==6.3.0` chạy trên `torch==2.15.0` (chạy local trên CPU, hỗ trợ đa ngôn ngữ bao gồm tiếng Việt và thuật ngữ tiếng Anh chuyên ngành).
  - **Số chiều vector:** `384` chiều (chuẩn hóa độ dài L2 `normalize_embeddings=True`).
- **Vector store & phiên bản:**
  - **Hệ quản trị:** **PostgreSQL `16.16`** tích hợp extension **`pgvector 0.8.7`** chạy qua Docker image `pgvector/pgvector:0.8.7-pg16` (cổng `127.0.0.1:55433`, kết nối qua `psycopg[binary]==3.3.8`).
  - **Cấu trúc lưu trữ & tính lũy đẳng (Idempotency):** Bảng `rag_chunks` lưu khóa chính định danh tất định `id` (ví dụ `A:fptu_so_tay_tsv_2026:p032:fixed:c001`), các cột metadata tường minh (`strategy`, `document_id`, `source`, `page`, `section`, `chunk_index`), JSONB `metadata`, nội dung `content` và cột `embedding vector(384)`. Hàm `upsert()` trong [`starter/src/store.py`](../../starter/src/store.py) sử dụng `ON CONFLICT (id) DO UPDATE` kết hợp xóa các chunk cũ không còn nằm trong tập ID hiện hành của chiến lược đó. Khi chạy nạp lặp lại lần 2 trên cùng dữ liệu, số bản ghi giữ nguyên tuyệt đối (`263 -> 263` đối với Strategy A; `175 -> 175` đối với Strategy B và C).
- **Metric tìm kiếm tương đồng:**
  - **Exact Cosine Similarity:** Tính bằng `1 - (embedding <=> query_vector)` sử dụng toán tử khoảng cách cosine `<=>` của `pgvector`.
- **Lệnh chạy tái lập toàn bộ thực nghiệm:**
  ```powershell
  # 1. Khởi động PostgreSQL + pgvector container
  cd starter
  docker compose up -d

  # 2. Kiểm tra kết nối DB và extension pgvector
  python scripts/check_setup.py

  # 3. Chạy toàn bộ pipeline nạp dữ liệu (A/B/C), kiểm tra idempotency và chấm benchmark (dev/test)
  python -m src.run
  ```
- **Thời gian thực thi và chi phí:**
  - **Thời gian chạy:** Nạp và nhúng vector mất `7,327s` (Strategy A – 263 chunks), `5,122s` (Strategy B – 175 chunks), và `5,029s` (Strategy C – 175 chunks). Tổng thời gian chạy toàn bộ pipeline (gồm cả nạp lặp lần 2 kiểm tra idempotency và truy vấn 20 câu hỏi × 3 chiến lược) là **~18,5 giây**.
  - **Chi phí:** **`$0.00 USD`** (sử dụng mô hình local trên CPU, không phát sinh chi phí gọi API thương mại).

### Metadata bắt buộc, trường lọc bổ sung, nguồn giá trị và lý do chọn
- **3 trường metadata bắt buộc trên mọi chunk:**
  1. `document_id`: `"fptu_so_tay_tsv_2026"` — định danh duy nhất của tài liệu.
  2. `source`: `"data/2026_So-tay-TSV_compressed.pdf"` — đường dẫn tới file nguồn.
  3. `page`: Số nguyên (`int`) biểu thị trang vật lý trong file PDF (`8..110`) nơi trích xuất đoạn văn bản.
- **Trường metadata bổ sung phục vụ lọc (`filter_section`):**
  - `section`: Mã chương chuẩn hóa (gồm 9 giá trị: `01_tong_quan_fptu`, `02_noi_quy_sinh_vien`, `03_quy_che_dao_tao`, `04_tai_chinh_hoc_phi`, `05_ho_tro_sinh_vien`, `06_khao_thi`, `07_thu_vien_it`, `08_doi_song_sinh_vien`, `09_thong_tin_lien_he`), đi kèm `section_title` (tên chương tiếng Việt).
  - **Nguồn giá trị:** Được ánh xạ tất định (deterministic mapping) dựa trên dải trang của 9 chương trong Mục lục chính thức của sổ tay (trang 4–5).
  - **Lý do chọn `section` làm trường lọc:** Trong tài liệu quy chế đại học, nhiều chương khác nhau sử dụng chung các thuật ngữ học vụ (ví dụ: từ khóa *"học lại"*, *"tín chỉ"*, *"đình chỉ"*, *"vi phạm quy chế"* xuất hiện đồng thời ở Chương 2 Nội quy sinh viên, Chương 3 Quy chế đào tạo, Chương 4 Tài chính – Học phí và Chương 6 Khảo thí). Khi người dùng hỏi cụ thể về quy định tài chính hay quy định khảo thí, lọc theo `section` giúp loại bỏ triệt để hiện tượng lấy nhầm đoạn văn có từ vựng tương tự ở chương khác.

---

## 2. Cấu hình và benchmark

### Ba cấu hình thử nghiệm A / B / C (tham số cụ thể và khác biệt duy nhất B–C)
Cả ba chiến lược đều chạy trên **cùng một tập văn bản 94 trang hợp lệ**, **cùng mô hình embedding (`paraphrase-multilingual-MiniLM-L12-v2`, 384 chiều)**, **cùng cơ sở dữ liệu `pgvector`** và **cùng bộ 20 câu hỏi benchmark**:

1. **Strategy A — Baseline (`fixed_size`, không dùng metadata filter):**
   - Cách chia chunk: Cắt theo cửa sổ độ dài ký tự cố định `chunk_size = 500` ký tự, độ chồng lấp `overlap = 50` ký tự trên từng trang (`fixed_size` trong [`starter/src/chunking.py`](../../starter/src/chunking.py)).
   - Bộ lọc khi truy vấn: Không lọc (`use_metadata_filter = False`).
   - Số lượng chunk sinh ra: `263` chunks (độ dài trung bình `416,6` ký tự, ngắn nhất `56`, dài nhất `500`).
2. **Strategy B — Chia theo cấu trúc đoạn văn (`by_paragraph`, không dùng metadata filter):**
   - Cách chia chunk: Tách theo ranh giới đoạn văn (`\n\n`) và các đề mục đánh số tự nhiên; gộp các đoạn ngắn liền kề cho tới ngưỡng tối đa `max_size = 850` ký tự, `overlap = 0` (`by_paragraph` trong [`starter/src/chunking.py`](../../starter/src/chunking.py)). Nếu một đoạn đơn lẻ dài quá `850` ký tự thì tách tại dấu kết thúc câu (`.`, `;`) gần nhất để không cắt ngang từ.
   - Bộ lọc khi truy vấn: Không lọc (`use_metadata_filter = False`).
   - Số lượng chunk sinh ra: `175` chunks (độ dài trung bình `576,6` ký tự, giảm `33,5%` số lượng chunk so với Strategy A).
3. **Strategy C — Chia theo cấu trúc đoạn văn + Lọc theo Metadata `section` (`by_paragraph` + `section` filter):**
   - Cách chia chunk: **Giữ nguyên 100% cấu hình chia chunk của Strategy B** (`by_paragraph`, `max_size = 850`, `overlap = 0`, sinh ra đúng `175` chunks có nội dung và vector y hệt Strategy B).
   - **Khác biệt duy nhất giữa B và C:** Bật bộ lọc metadata `WHERE section = %(section)s` (`use_metadata_filter = True`) trong câu truy vấn SQL đối với các câu hỏi có yêu cầu phạm vi chương/mục (`filter_section`). Thiết kế này đảm bảo phép so sánh có kiểm soát (controlled comparison) cô lập hoàn toàn tác động của bộ lọc metadata.

### Bộ câu hỏi Benchmark (≥20 câu: 15 dev / 5 test, câu metadata filter và cách kiểm chứng evidence)
- **Cấu trúc bộ câu hỏi ([`benchmark/questions.json`](../../benchmark/questions.json)):**
  - Gồm **`20` câu hỏi** hoàn chỉnh (`q01` đến `q20`), bao phủ cả 8 chương nội dung chính của sổ tay.
  - **Phân chia tập `dev` / `test` cố định trước khi chạy:**
    - Tập **`dev` (`15` câu, `q01`–`q15`):** Dùng để quan sát hành vi truy xuất, phân tích lỗi và chọn chiến lược tốt nhất.
    - Tập **`test` (`5` câu, `q16`–`q20`):** Giữ cố định để đánh giá khách quan sau khi đã chốt chiến lược từ tập `dev`.
  - **Câu hỏi có điều kiện lọc metadata (`6` câu, vượt mức tối thiểu `>= 3` câu):**
    - Trên tập `dev` (`4` câu): `q07` (`04_tai_chinh_hoc_phi`), `q09` (`04_tai_chinh_hoc_phi`), `q12` (`06_khao_thi`), `q13` (`06_khao_thi`).
    - Trên tập `test` (`2` câu): `q17` (`06_khao_thi`), `q18` (`07_thu_vien_it`).
- **Cách kiểm chứng bằng chứng chuẩn (`gold evidence verification`):**
  - Mỗi câu hỏi lưu kèm `gold_page` (trang vật lý chứa đáp án), `evidence_quote` (đoạn trích nguyên văn từ trang đó) và `alt_evidence_quotes` (các cụm thông tin cốt lõi cần xuất hiện để trả lời trọn vẹn câu hỏi).
  - Trước khi chạy thực nghiệm, toàn bộ 20 câu hỏi đã được kiểm chứng tự động bằng script đối chiếu chuỗi con trực tiếp trên văn bản đã chuẩn hóa của từng trang PDF: `20/20 (100%)` câu hỏi có `evidence_quote` và tất cả các mảnh trong `alt_evidence_quotes` khớp chính xác trên đúng `gold_page`.
  - Quy tắc tính hit tự động trong [`starter/src/evaluation.py`](../../starter/src/evaluation.py): Một chunk được tính là chứa bằng chứng hợp lệ (`evidence_hit`) khi: (1) thuộc đúng `gold_page` và chứa đầy đủ thông tin bằng chứng (`evidence_quote` hoặc toàn bộ các mảnh bắt buộc trong `alt_evidence_quotes`), và (2) nếu câu hỏi có `filter_section` thì chunk đó phải có `metadata.section == filter_section`.

### Tiêu chí chọn chiến lược đã chốt trước khi xem test
Trước khi xem kết quả tập `test`, quy tắc chọn chiến lược chiến thắng trên tập `dev` (15 câu) được cố định theo thứ tự ưu tiên:
1. Tối đa hóa **Evidence Hit@3 trên tập `dev`**.
2. Đạt tỷ lệ **Filter Compliance cao nhất trên tập `dev`** (tránh trả về chunk sai chương quy định).
3. Đạt điểm **Coherence trung bình** và **Hit@1 trên tập `dev`** cao hơn, đồng thời tối ưu số lượng chunk lưu trữ.

---

## 3. Kết quả

### Bảng 1: Kết quả truy xuất tự động, tài nguyên và chi phí

| Strategy | Split | Hit@1 (n/N) | Evidence Hit@3 (n/N) | Chunk count | Thời gian | Chi phí |
|---|---|---|---|---|---|---|
| **A** (`fixed_size`, 500/50, no filter) | `dev` | `10/15` (`66.67%`) | `13/15` (`86.67%`) | `263` | `7.33s` (ingest) / `0.21s` (eval) | `$0.00` |
| **A** (`fixed_size`, 500/50, no filter) | `test` | `3/5` (`60.00%`) | `4/5` (`80.00%`) | `263` | `7.33s` (ingest) / `0.07s` (eval) | `$0.00` |
| **B** (`by_paragraph`, max 850, no filter) | `dev` | `10/15` (`66.67%`) | `14/15` (`93.33%`) | `175` | `5.12s` (ingest) / `0.20s` (eval) | `$0.00` |
| **B** (`by_paragraph`, max 850, no filter) | `test` | `2/5` (`40.00%`) | `3/5` (`60.00%`) | `175` | `5.12s` (ingest) / `0.07s` (eval) | `$0.00` |
| **C** (`by_paragraph`, max 850, `section` filter) | `dev` | `10/15` (`66.67%`) | `14/15` (`93.33%`) | `175` | `5.03s` (ingest) / `0.20s` (eval) | `$0.00` |
| **C** (`by_paragraph`, max 850, `section` filter) | `test` | `2/5` (`40.00%`) | `3/5` (`60.00%`) | `175` | `5.03s` (ingest) / `0.07s` (eval) | `$0.00` |

### Bảng 2: Kết quả Audit thủ công (Coherence, Metadata Usefulness, Grounding Quality)

| Strategy | Coherence trung bình /2 (n) | Metadata đủ và đúng (n/N) | Filter tuân thủ (n/N hoặc N/A) | Grounding 0/1/2 (số câu) và trung bình /2 |
|---|---|---|---|---|
| **A** (`fixed_size`, 500/50, no filter) | `0.90 / 2.00` (`n=10`: `3` mức 0, `5` mức 1, `2` mức 2) | `15/15` (`100%`) trên top-3 test | Dev: `3/4` (`75.0%`)<br>Test: `2/2` (`100.0%`)<br>Tổng: `5/6` (`83.3%`) | `0 / 0 / 5` (0 câu mức 0; 0 câu mức 1; 5 câu mức 2)<br>Trung bình: **`2.00 / 2.00`** |
| **B** (`by_paragraph`, max 850, no filter) | `1.70 / 2.00` (`n=10`: `0` mức 0, `3` mức 1, `7` mức 2) | `15/15` (`100%`) trên top-3 test | Dev: `3/4` (`75.0%`)<br>Test: `1/2` (`50.0%`)<br>Tổng: `4/6` (`66.7%`) | `0 / 2 / 3` (0 câu mức 0; 2 câu mức 1; 3 câu mức 2)<br>Trung bình: **`1.60 / 2.00`** |
| **C** (`by_paragraph`, max 850, `section` filter) | `1.70 / 2.00` (`n=10`: `0` mức 0, `3` mức 1, `7` mức 2) | `15/15` (`100%`) trên top-3 test | Dev: `4/4` (`100.0%`)<br>Test: `2/2` (`100.0%`)<br>Tổng: **`6/6` (`100.0%`)** | `0 / 2 / 3` (0 câu mức 0; 2 câu mức 1; 3 câu mức 2)<br>Trung bình: **`1.60 / 2.00`** |

### Đường dẫn trace, nhãn thủ công và cách chọn mẫu
- **Hồ sơ kết quả và log thực thi:**
  - Nhật ký nạp dữ liệu & lọc trang: [`results/ingestion_log.json`](../../results/ingestion_log.json)
  - Thống kê số lượng chunk, độ dài chunk, thời gian chạy và kiểm tra idempotency: [`results/strategy_stats.json`](../../results/strategy_stats.json)
  - Tổng hợp các chỉ số đánh giá tự động trên `dev` và `test`: [`results/metrics_summary.json`](../../results/metrics_summary.json)
  - Trace chi tiết Top-3 chunks trả về cho toàn bộ 20 câu hỏi × 3 chiến lược (60 truy vấn): [`results/traces.json`](../../results/traces.json)
  - Nhãn chấm điểm Audit thủ công chi tiết: [`results/manual_audit.json`](../../results/manual_audit.json)
  - Nhật ký cấu hình và giả thuyết thí nghiệm: [`artifacts/experiment_log.csv`](../../artifacts/experiment_log.csv)
- **Quy tắc chọn mẫu cố định cho Audit thủ công:**
  1. **Mẫu chấm Chunk Coherence (`n = 10` vị trí cố định):** Chọn chunk đầu tiên (`c001`) của 10 trang nội dung hợp lệ đầu tiên liên tiếp trong tài liệu (`trang 8, 9, 10, 11, 12, 14, 15, 16, 17, 18` — trang 13 là trang bìa ngăn Chương II nên đã bị loại ở bước ingestion). So sánh trực tiếp cùng một vị trí đầu trang giữa Strategy A (`pXXX:fixed:c001`) và Strategy B/C (`pXXX:para:c001`) theo thang điểm `0` (cắt ngang từ/mất ngữ cảnh nghiêm trọng), `1` (hiểu được ý chính nhưng cụt đầu/cuối hoặc trộn cột bảng), `2` (đoạn văn trọn vẹn, tự nhiên).
  2. **Mẫu chấm Metadata Usefulness (`15` bản ghi top-3 trên tập `test` mỗi chiến lược):** Kiểm tra toàn bộ `5 câu hỏi test (q16..q20) × 3 kết quả đầu = 15 bản ghi` cho mỗi chiến lược về tính đầy đủ/chính xác của `document_id`, `source`, `page`, `section` và kiểm tra tính tuân thủ bộ lọc trên các câu hỏi có `filter_section` (`q07, q09, q12, q13` ở `dev` và `q17, q18` ở `test`).
  3. **Mẫu chấm Grounding Quality (`n = 5` câu hỏi tập `test`: `q16`–`q20`):** Chấm khả năng trả lời dựa trên hợp nhất Top-3 chunks trả về của từng câu hỏi trong tập `test` theo thang điểm `0` (không có căn cứ), `1` (có một phần căn cứ nhưng thiếu ý phụ), `2` (đầy đủ căn cứ trả lời chính xác mọi vế của câu hỏi).

---

## 4. Phân tích và kết luận

### So sánh có kiểm soát A–B và B–C kèm các ví dụ lỗi cụ thể từ Trace

#### 1. So sánh A và B (Tác động của thuật toán chia chunk: `fixed_size` 500/50 vs. `by_paragraph` max 850)
- **Về độ mạch lạc (Coherence) và hiệu quả lưu trữ:** Strategy A cắt cứng ở mốc 500 ký tự nên có tới `3/10` mẫu audit bị điểm `0` và `5/10` mẫu bị điểm `1` (điểm trung bình chỉ đạt **`0.90/2.00`**), do thường xuyên cắt đôi từ tiếng Việt ở cuối chunk (ví dụ trang 8 bị cắt ngang chữ `"...năng lực cạnh tr"` trong *"cạnh tranh"*, trang 9 cắt ngang chữ `"...học t"` trong *"học tập"*). Ngược lại, Strategy B tôn trọng ranh giới đoạn văn `\n\n` và đề mục đánh số nên không có bất kỳ chunk nào bị điểm `0`, nâng điểm Coherence trung bình lên **`1.70/2.00`** đồng thời giảm `33,5%` số lượng chunk cần lưu trữ (`175` so với `263` chunks) và giảm `30,1%` thời gian nạp (`5,12s` so với `7,33s`).
- **Về độ chính xác truy xuất trên tập `dev`:** Strategy B nâng **Evidence Hit@3 trên tập `dev` từ `13/15 (86,67%)` lên `14/15 (93,33%)`**.
- **Ví dụ lỗi 1 — `q07` (tập `dev`, nguồn: trang 32, Chương 4 `04_tai_chinh_hoc_phi`):**
  - *Câu hỏi:* *"Mức học phí học lại trên mỗi tín chỉ được tính bằng bao nhiêu phần trăm so với biểu phí chuẩn và áp dụng tương tự cho chương trình nào?"*
  - *Bằng chứng gốc (trang 32):* Nằm ở đoạn văn quy định học phí học lại: `"Học phí học lại tính trên đơn vị tín chỉ và bằng 50% học phí tính theo tín chỉ tương ứng tại biểu phí học kỳ chính... Học phí học lại các học phần trong chương trình dự bị tiếng Anh cũng áp dụng cách tính tương tự với mức học phí bằng 50% biểu phí chuẩn."`
  - *Hành vi của Strategy A (Thất bại — Miss):* Do cắt cứng 500 ký tự, đoạn văn này bị xẻ làm đôi giữa hai chunk: `A:fptu_so_tay_tsv_2026:p032:fixed:c002` (chứa vế đầu *"bằng 50% học phí tính theo tín chỉ"* nhưng bị cắt cụt ở chữ `"tương ứng v"`) và `A:fptu_so_tay_tsv_2026:p032:fixed:c003` (chứa vế sau *"chương trình dự bị tiếng Anh"*). Khi truy vấn, Strategy A chỉ đưa được `c003` vào vị trí Rank 2 (`score = 0.7289`), còn `c002` bị đẩy văng khỏi Top-3 (nhường chỗ cho trang 35 và trang 33). Do `c003` mất câu đầu giải thích cách tính trên đơn vị tín chỉ, Strategy A không đạt chuẩn bằng chứng trên một chunk.
  - *Hành vi của Strategy B & C (Thành công tại Rank 1):* Thuật toán `by_paragraph` giữ nguyên cả đoạn quy định học phí học lại trong một chunk duy nhất `p032:para:c002` (dài 688 ký tự). Nhờ ngữ nghĩa đầy đủ, chunk này đạt điểm tương đồng rất cao (`score = 0.7524`) và đứng ngay vị trí **Rank 1** ở cả Strategy B và C.

#### 2. So sánh B và C (Tác động thuần túy của bộ lọc Metadata `section`)
- Vì Strategy B và C dùng chung tập 175 chunks, sự khác biệt giữa B và C phản ánh chính xác tác dụng của bộ lọc `WHERE section = %(section)s`. Khi bật bộ lọc ở Strategy C, **Filter Compliance tăng từ `3/4 (75%)` lên `4/4 (100%)` trên tập `dev`** và **từ `1/2 (50%)` lên `2/2 (100%)` trên tập `test`**.
- **Ví dụ lỗi 2 — `q09` (tập `dev`, trang 36, `04_tai_chinh_hoc_phi`) và `q17` (tập `test`, trang 57, `06_khao_thi`):**
  - *Trường hợp `q09` (Tập `dev`):* Câu hỏi hỏi trong phạm vi chương **Tài chính – Học phí** (`04_tai_chinh_hoc_phi`): *"Sinh viên bảo lưu học kỳ vì lý do cá nhân phải nộp đơn trước thời điểm nào và khoản học phí đã nộp sẽ được xử lý ra sao?"* (Đáp án chuẩn ở trang 36).
    - Ở **Strategy B (không filter)**, tuy Rank 1 lấy đúng `B:fptu_so_tay_tsv_2026:p036:para:c001` (`score = 0.7330`), nhưng Rank 2 (`p020:para:c001`, `score = 0.7155`) và Rank 3 (`p021:para:c002`, `score = 0.7131`) lại bị **rò rỉ sang Chương 3 Quy chế đào tạo (`03_quy_che_dao_tao`)** do trang 20–21 cũng lặp lại dày đặc cụm từ *"nghỉ học tạm thời"*, *"bảo lưu"* và *"bắt đầu học kỳ mới"*.
    - Ở **Strategy C (bật filter `section = 04_tai_chinh_hoc_phi`)**, các chunk gây nhiễu từ Chương 3 bị loại bỏ hoàn toàn; cả 3 vị trí Top-3 (`p036:para:c001`, `p033:para:c001`, `p032:para:c002`) đều nằm đúng trong Chương 4 Tài chính – Học phí.
  - *Trường hợp `q17` (Tập `test`):* Câu hỏi hỏi trong phạm vi chương **Khảo thí** (`06_khao_thi`): *"Sinh viên vi phạm quy chế thi ở mức đình chỉ thi học phần sẽ bị xử lý điểm và điều kiện học tập của môn đó như thế nào?"* (Đáp án chuẩn ở trang 57: nhận điểm 0 và phải học lại).
    - Ở **Strategy B (không filter)**, vị trí Rank 3 trả về chunk `B:fptu_so_tay_tsv_2026:p018:para:c002` (`score = 0.7285`) thuộc **Chương 2 Nội quy sinh viên (`02_noi_quy_sinh_vien`)** nói về khung kỷ luật chung của nhà trường, làm vi phạm điều kiện lọc chương (`filter_compliant = False`).
    - Ở **Strategy C (bật filter `section = 06_khao_thi`)**, kết quả được giới hạn chặt trong Chương 6 Khảo thí (`p057:para:c002` ở Rank 1, `p057:para:c001` ở Rank 2 và `p056:para:c001` ở Rank 3), đạt `100%` tuân thủ bộ lọc và cung cấp ngữ cảnh khảo thí hoàn toàn nhất quán.

#### 3. Ví dụ lỗi 3 — Hiện tượng bằng chứng vắt qua hai đoạn văn (`q15` trang 92 tập `dev`, `q18` trang 65 và `q19` trang 75 tập `test`)
- Một phát hiện thực nghiệm rất đáng chú ý là trên câu `q15` (trang 92, tập `dev`) cũng như hai câu `q18` (trang 65) và `q19` (trang 75) của tập `test`, câu hỏi gồm **2 vế thông tin nằm ở 2 đoạn văn/mục đánh số kế tiếp nhau trên cùng một trang**:
  - Ở **`q15` (trang 92, tập `dev`)**: Vế 1 (chu kỳ hoạt động của CLB từ đầu kỳ Mùa Thu đến hết kỳ Mùa Hè năm kế tiếp) nằm ở mục `1. Nguyên tắc đánh giá` (`p092:para:c001`), còn Vế 2 (7 tiêu chí đánh giá AVO) lại nằm ở đoạn tiếp theo (`p092:para:c002`). Cả Strategy B và C đều lấy đúng cả `p092:para:c002` (Rank 1) và `p092:para:c001` (Rank 2) vào trong Top-3 (`evidence_split_across_chunks = True`), nhưng vì mỗi chunk chỉ chứa một vế nên chỉ số tự động đơn-chunk `Evidence Hit@3` ghi nhận là Miss.
  - Ở **`q19` (trang 75, tập `test`)**: Câu hỏi hỏi về (1) việc dùng Macbook trong quá trình học và (2) điều kiện bắt buộc khi tham gia kỳ thi trên máy tính (cài máy ảo Windows hoặc mượn máy Windows). Trên trang 75, hai ý này nằm ở hai gạch đầu dòng dài tách biệt (`p075:para:c001` dài 741 ký tự và `p075:para:c002` dài 835 ký tự; tổng cộng 1.576 ký tự > `max_size = 850` nên `by_paragraph` buộc phải tách thành 2 chunks). Khi truy vấn, Strategy B và C lấy được `p075:para:c002` ở **Rank 1** (`score = 0.7289`, trả lời được quy định thi bằng máy ảo/Windows), nhưng ở Rank 2 và Rank 3 mô hình lại xếp chunk cấu hình laptop ở trang 72 (`0.6889`) và trang 74 (`0.6786`) cao hơn `p075:para:c001`, khiến Grounding đạt mức `1/2` (trả lời đúng quy định thi nhưng thiếu trích dẫn trực tiếp câu khẳng định được phép dùng Macbook khi học trên lớp). Trong khi đó, ở Strategy A (`fixed_size` 500/50), nhờ chia nhỏ hơn và có overlap 50 ký tự, cả `p075:fixed:c002` (Rank 1) và `p075:fixed:c003` (Rank 3) đều lọt vào Top-3 nên hợp nhất Top-3 của Strategy A đủ cả 2 vế (Grounding đạt `2/2`, dù đơn-chunk `Evidence Hit@3` vẫn tính là Miss vì hai vế nằm ở 2 chunk khác nhau).

### Chiến lược được chọn, đánh đổi và điều kiện áp dụng
- **Chiến lược được chọn ( theo tiêu chí đã chốt trên tập `dev`):** **Strategy C (`by_paragraph`, `max_size = 850`, `overlap = 0` kết hợp Metadata Filter trên `section`)**.
- **Lý do chọn:**
  1. Đạt **Evidence Hit@3 cao nhất trên tập `dev` (`14/15 = 93,33%`)**, vượt Strategy A (`13/15 = 86,67%`).
  2. Đạt **Filter Compliance tuyệt đối `100%` trên cả tập `dev` (`4/4`) và tập `test` (`2/2`)**, khắc phục hoàn toàn lỗi rò rỉ ngữ cảnh chéo chương của Strategy A và B.
  3. Đạt điểm **Coherence trung bình cao gấp gần 2 lần Strategy A (`1.70/2.00` so với `0.90/2.00`)**, giữ nguyên cấu trúc điều khoản quy chế để LLM hoặc người đọc dễ kiểm chứng nguồn.
  4. Tiết kiệm **`33,5%` dung lượng lưu trữ vector** (`175` chunks so với `263` chunks) và tăng tốc độ nạp thêm **`31,4%`** (`5,03s` so với `7,33s`).
- **Sự đánh đổi (Trade-offs):**
  - *Đánh đổi giữa tính trọn vẹn của đoạn văn (`by_paragraph`, `overlap = 0`) và khả năng bắt bằng chứng liên đoạn:* Khi không dùng overlap giữa các đoạn văn và đặt `max_size = 850`, nếu một câu hỏi tổng hợp yêu cầu ghép thông tin từ 2 đoạn văn dài liên tiếp trên cùng một trang (như `q18` trang 65 và `q19` trang 75 trên tập `test`), một trong hai đoạn có thể có độ tương đồng vector thấp hơn các đoạn cùng chủ đề ở trang khác và rơi khỏi Top-3.
  - *Đánh đổi khi dùng Metadata Filter cứng (`WHERE section = ...`):* Đảm bảo độ chính xác phạm vi 100% khi biết đúng chương/mục cần tra cứu, nhưng đòi hỏi hệ thống upstream (UI bộ lọc hoặc bộ phân loại ý định truy vấn / query router) phải gán đúng nhãn `section`; nếu người dùng chọn sai chương lọc thì câu trả lời đúng nằm ở chương khác sẽ bị loại.
- **Điều kiện áp dụng tốt nhất:** Phù hợp cho các tài liệu quy chế, sổ tay nghiệp vụ, văn bản pháp quy hoặc tài liệu kỹ thuật có cấu trúc chương/mục rõ ràng và người dùng (hoặc agent router) có thể xác định phân vùng nội dung cần tra cứu.

### Hạn chế của dữ liệu, nhãn, tập test nhỏ và đo thời gian/chi phí
1. **Hạn chế của dữ liệu PDF gốc:** Tài liệu có một số trang thiết kế đồ họa 2 cột hoặc bảng biểu phức tạp (trang 10, 17, 18, 86–90). Trình trích xuất văn bản tuần tự `pypdf` chưa tái tạo lại cấu trúc bảng Markdown (hàng/cột), dẫn đến việc tiêu đề cột và giá trị ô bị xếp nối tiếp nhau.
2. **Hạn chế của kích thước tập `test` nhỏ (`N = 5` câu):** Với quy mô 5 câu hỏi trên tập `test`, mỗi câu hỏi tương ứng với bước nhảy **`20%`** trên các chỉ số `Hit@1` và `Evidence Hit@3`. Do đó, việc chênh lệch 1 câu hỏi giữa Strategy A (`4/5 = 80%`) và Strategy B/C (`3/5 = 60%`) chịu ảnh hưởng lớn bởi phương sai mẫu nhỏ (cụ thể là các câu hỏi đa đoạn như `q18` và `q19`).
3. **Hạn chế của đánh giá thủ công (Single-annotator bias):** Các nhãn `Coherence` và `Grounding` do một người thực hiện chấm dựa trên rubric nên dù đã cố định vị trí lấy mẫu và ghi rõ lý giải từng điểm trong `results/manual_audit.json`, vẫn có thể tồn tại sai số chủ quan nhất định so với việc có nhiều giám khảo chấm độc lập (inter-annotator agreement).
4. **Hạn chế trong đo thời gian và chi phí:** Thời gian thực thi được đo trên môi trường máy cá nhân (local CPU + Docker container trên cùng máy chủ localhost), nên độ trễ mạng gần như bằng 0 và tốc độ nhúng phụ thuộc vào xung nhịp CPU tại thời điểm chạy.

### Nếu làm lại hoặc mở rộng, cần cải tiến gì?
1. **Bổ sung Paragraph-level Overlap (Sliding Paragraph Window) cho `by_paragraph`:** Thay vì `overlap = 0` giữa các chunk đoạn văn, giữ lại `1` đoạn ngắn hoặc `1–2` câu cuối (~100–150 ký tự) của chunk trước làm phần mở đầu cho chunk kế tiếp trên cùng một trang, hoặc cho phép gộp các mục con cùng một điều khoản lên ngưỡng `1.000–1.200` ký tự. Cải tiến này sẽ giải quyết trực tiếp lỗi tách đôi bằng chứng ở `q15` (trang 92), `q18` (trang 65) và `q19` (trang 75) mà vẫn giữ nguyên điểm Coherence cao (`1.70/2.00`).
2. **Gắn Contextual Header vào nội dung chunk trước khi tạo Embedding:** Tự động chèn dòng tiêu đề ngữ cảnh `[Chương: <section_title> | Trang <page> | Mục hiện hành]` vào đầu mỗi chunk trước khi đưa qua model embedding. Khi đó, cả những đoạn văn ngắn chỉ chứa mức phạt hoặc điều kiện phụ (như đoạn nói về quá hạn 30 ngày ở `q18` hay đoạn dùng Macbook khi học ở `q19`) vẫn mang đầy đủ ngữ cảnh chủ đề chính để đạt điểm cosine similarity cao.
3. **Kết hợp Hybrid Search (Dense Vector `pgvector` + Full-Text Search `tsvector` / BM25 với Reciprocal Rank Fusion):** Các câu hỏi chứa mã môn học, con số chính xác hoặc tên viết tắt đặc thù của trường (như `LUK`, `TRANS 5`, `ENT501`, `VNR202`, `AVO`, `1900 636 961`, `5.000 đ/ngày`) sẽ được bắt chính xác hơn khi kết hợp điểm khớp từ khóa BM25 cùng điểm tương đồng ngữ nghĩa của `paraphrase-multilingual-MiniLM-L12-v2`.
4. **Trích xuất PDF nhận diện bố cục bảng (Layout-aware PDF Parsing):** Sử dụng công cụ nhận diện cấu trúc bảng/cột (như `pdfplumber` hoặc `Docling`) để chuyển các bảng quy chế kỷ luật (trang 17–18) và bảng lộ trình tiếng Anh (trang 10) sang định dạng bảng Markdown chuẩn trước khi chia chunk.

