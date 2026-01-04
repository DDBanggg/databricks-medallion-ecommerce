# Olist E-commerce Lakehouse Project

## 1. Giới thiệu (Overview)
Dự án xây dựng Data Lakehouse cho bộ dữ liệu Olist (Sàn thương mại điện tử Brazil).
Hệ thống được thiết kế để xử lý dữ liệu từ dạng thô (Raw) đến dạng tinh chỉnh phục vụ báo cáo (Analytics Ready) trên nền tảng Databricks.

## 2. Mục tiêu (Objectives)
* **Centralize Data:** Tập trung dữ liệu từ nhiều nguồn CSV/JSON về Delta Lake.
* **Data Quality:** Đảm bảo dữ liệu sạch, đúng kiểu dữ liệu và loại bỏ trùng lặp.
* **Business Intelligence:** Cung cấp các bảng Fact/Dimension để phân tích doanh thu, hành vi khách hàng và hiệu quả vận chuyển.

## 3. Kiến trúc (Architecture)
Dự án áp dụng **Medallion Architecture** (Multi-hop architecture):

### 🏗️ Bronze Layer (Ingestion)
* **Nguồn:** Raw CSV files (S3/ADLS/DBFS).
* **Xử lý:** Đọc dữ liệu thô, giữ nguyên gốc (raw), thêm metadata (ingestion_date, file_name).
* **Format:** Delta Table (Append Only).

### ⚙️ Silver Layer (Transformation)
* **Nguồn:** Bronze Tables.
* **Xử lý:**
    * Data Cleaning (xử lý Null, định dạng lại ngày tháng).
    * Deduplication (loại bỏ bản ghi trùng).
    * Enforce Schema (áp dụng schema chuẩn từ `config/`).
    * Joins (nếu cần thiết để denormalize nhẹ).

### 📊 Gold Layer (Aggregation)
* **Nguồn:** Silver Tables.
* **Xử lý:** Tính toán các chỉ số kinh doanh (KPIs), tạo Star Schema (Fact/Dim).
* **Mục đích:** Phục vụ trực tiếp cho Dashboard (PowerBI, Tableau, Databricks SQL).

## 4. Cách sử dụng (How to run)
1.  Cài đặt thư viện: `pip install -r requirements.txt`
2.  Cấu hình tham số trong `config/pipeline_config.yaml`.
3.  Chạy pipeline theo thứ tự:
    * Run `pipelines/01_bronze_ingestion/*`
    * Run `pipelines/02_silver_transformation/*`
    * Run `pipelines/03_gold_aggregation/*`

## 5. Tech Stack
* **Language:** Python (PySpark), SQL.
* **Storage:** Delta Lake.
* **Orchestration:** Databricks Workflows.