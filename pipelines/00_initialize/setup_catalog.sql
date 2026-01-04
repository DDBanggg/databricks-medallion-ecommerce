-- 1. Tạo Catalog (Top-level container)
-- Catalog là cấp cao nhất trong Unity Catalog, chứa schemas và các đối tượng dữ liệu.
CREATE CATALOG IF NOT EXISTS olist_catalog
COMMENT 'Catalog chứa toàn bộ dữ liệu cho dự án Olist Ecommerce Lakehouse';

-- Chuyển context sang catalog vừa tạo để các lệnh sau không cần gõ lại prefix 'olist_catalog.'
USE CATALOG olist_catalog;

-- ---------------------------------------------------------
-- 2. Tạo các Schema (Tầng dữ liệu - Medallion Architecture)
-- ---------------------------------------------------------

-- 2.1 Schema Bronze: Nơi hạ cánh của dữ liệu thô
CREATE SCHEMA IF NOT EXISTS bronze
COMMENT 'Layer 1: Chứa dữ liệu thô (Raw Data), giữ nguyên định dạng gốc từ nguồn (Ingestion)';

-- 2.2 Schema Silver: Dữ liệu đã làm sạch và chuẩn hóa
CREATE SCHEMA IF NOT EXISTS silver
COMMENT 'Layer 2: Chứa dữ liệu đã được làm sạch (Cleaned), xử lý null, deduplicate và chuẩn hóa schema';

-- 2.3 Schema Gold: Dữ liệu tổng hợp theo nghiệp vụ
CREATE SCHEMA IF NOT EXISTS gold
COMMENT 'Layer 3: Chứa dữ liệu đã tổng hợp (Aggregated), thường ở dạng Star Schema (Fact/Dim) để phân tích';

-- 2.4 Schema Business: Dữ liệu sẵn sàng cho báo cáo
CREATE SCHEMA IF NOT EXISTS business
COMMENT 'Layer 4: Chứa các Views hoặc bảng được tối ưu hóa riêng cho các công cụ BI (PowerBI, Tableau)';

-- ---------------------------------------------------------
-- 3. Tạo Volume (Storage cho File)
-- ---------------------------------------------------------

-- Tạo Managed Volume trong schema Bronze để chứa file CSV
-- Volume trong Unity Catalog hoạt động giống như một folder trong hệ thống file, giúp quản lý file phi cấu trúc.
CREATE VOLUME IF NOT EXISTS bronze.raw_data
COMMENT 'Nơi lưu trữ các file CSV dataset Olist được upload lên từ local';