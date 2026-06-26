-- =====================================================
-- PROJECT  : Analisis Kohort & Pemodelan CLV untuk Optimasi Peluncuran Produk B2B
-- DATABASE : retail_b2b
-- DATASET  : Online Retail II (Kaggle / UCI ML Repository)
-- AUTHOR   : <nama-kamu>
-- =====================================================
-- STRUKTUR FILE INI:
--   STEP 0  Import data mentah (raw_transactions)
--   STEP 1  Pembersihan whitespace Description
--   STEP 2  Pembentukan tabel bersih (cleaned_transactions)
--   STEP 3  Cohort analysis (cohort_analysis)
--   STEP 4  Retention rate per cohort (cohort_retention_rate)
--   STEP 5  Export untuk tahap Python (RFM & K-Means)
--
-- CATATAN PENTING SEBELUM MENJALANKAN:
--   1. Aktifkan local_infile di server (lihat STEP 0)
--   2. Di MySQL Workbench, tambahkan OPT_LOCAL_INFILE=1 di
--      Edit Connection > Advanced > Others, lalu reconnect
--   3. Statement BERAT (UPDATE besar, CREATE TABLE dari SELECT
--      jutaan baris) SEBAIKNYA dijalankan lewat MySQL Command
--      Line Client (mysql -u root -p), BUKAN Workbench — karena
--      Workbench punya batas read-timeout default yang terlalu
--      singkat untuk operasi ini dan akan memutus koneksi
--      (Error 2013: Lost connection) meski query sebenarnya
--      tetap berjalan/berhasil di server.
-- =====================================================


-- =====================================================
-- STEP 0 : IMPORT DATASET MENTAH
-- =====================================================
CREATE DATABASE IF NOT EXISTS retail_b2b CHARACTER SET utf8mb4;
USE retail_b2b;

SET GLOBAL local_infile = 1;

DROP TABLE IF EXISTS raw_transactions;

CREATE TABLE raw_transactions (
    Invoice      VARCHAR(20),
    StockCode    VARCHAR(20),
    Description  VARCHAR(255),
    Quantity     INT,
    InvoiceDate  DATETIME,
    Price        DECIMAL(10,3),   -- 3 digit desimal: menghindari truncation untuk nilai seperti 0.001
    CustomerID   INT NULL,
    Country      VARCHAR(100)
) CHARACTER SET utf8mb4;

LOAD DATA LOCAL INFILE 'D:/b2b-cohort-clv-optimization/online_retail_II.csv'
INTO TABLE raw_transactions
CHARACTER SET utf8mb4
FIELDS TERMINATED BY ','
ENCLOSED BY '"'
LINES TERMINATED BY '\n'           -- bukan \r\n: MySQL sudah otomatis menangani \r Windows
IGNORE 1 ROWS
(
    Invoice,
    StockCode,
    Description,
    Quantity,
    InvoiceDate,                   -- format file sudah YYYY-MM-DD HH:MM:SS, tidak perlu STR_TO_DATE
    Price,
    @CustomerID,
    Country
)
SET
    CustomerID = IF(@CustomerID = '', NULL, @CustomerID);

-- --- Verifikasi import ---------------------------------------------------
SELECT COUNT(*) AS total_baris FROM raw_transactions;          -- target: 1.067.371

SELECT * FROM raw_transactions LIMIT 10;

SELECT COUNT(*) AS invoicedate_null
FROM raw_transactions
WHERE InvoiceDate IS NULL;                                     -- target: 0

SELECT COUNT(*) AS customerid_null
FROM raw_transactions
WHERE CustomerID IS NULL;                                       -- normal: ~243.000 (karakteristik dataset)

SELECT MIN(InvoiceDate) AS tanggal_awal, MAX(InvoiceDate) AS tanggal_akhir
FROM raw_transactions;                                          -- target: 2009-12-01 s/d 2011-12-09


-- =====================================================
-- STEP 1 : PEMBERSIHAN WHITESPACE PADA DESCRIPTION
-- =====================================================
-- Dilakukan di raw_transactions SEBELUM membentuk cleaned_transactions,
-- supaya tabel hasil cleaning langsung final tanpa perlu UPDATE susulan.
-- >>> JALANKAN VIA COMMAND LINE (mysql -u root -p), bukan Workbench <

SET SQL_SAFE_UPDATES = 0;

UPDATE raw_transactions
SET Description = TRIM(REGEXP_REPLACE(Description, '\\s+', ' '));

SET SQL_SAFE_UPDATES = 1;

-- --- Verifikasi tidak ada lagi spasi ganda --------------------------------
SELECT COUNT(*) AS sisa_spasi_ganda
FROM raw_transactions
WHERE Description LIKE '%  %';
-- Targetnya: 0


-- =====================================================
-- STEP 2 : MEMBUAT TABEL BERSIH (cleaned_transactions)
-- =====================================================
-- Aturan exclude:
--   1. CustomerID NULL           -> transaksi tidak bisa dilacak ke pelanggan
--   2. StockCode administratif   -> ongkos kirim, biaya bank, fee Amazon, dll (bukan produk)
--   3. Description catatan internal (rusak/hilang/dsb), bukan deskripsi produk asli
-- Kolom tambahan:
--   is_return    : 1 jika Invoice diawali 'C' (Invoice pembatalan/retur)
--   LineRevenue  : Quantity * Price (otomatis negatif untuk baris retur)
-- >>> JALANKAN VIA COMMAND LINE (mysql -u root -p), bukan Workbench <

DROP TABLE IF EXISTS cleaned_transactions;

CREATE TABLE cleaned_transactions AS
SELECT
    Invoice,
    StockCode,
    Description,
    Quantity,
    InvoiceDate,
    Price,
    CustomerID,
    Country,
    CASE WHEN Invoice LIKE 'C%' THEN 1 ELSE 0 END AS is_return,
    (Quantity * Price) AS LineRevenue
FROM raw_transactions
WHERE
    CustomerID IS NOT NULL
    AND StockCode NOT IN ('POST','D','C2','DOT','M','m','BANK CHARGES','CRUK','AMAZONFEE','S','B')
    AND (Description IS NULL OR Description NOT REGEXP
        'destroyed|unsaleable|damaged|missing|adjustment|mouldy|smashed|crushed|thrown away|wrongly coded|sold as set|water damage|rusty|wet damaged');

CREATE INDEX idx_customer    ON cleaned_transactions (CustomerID);
CREATE INDEX idx_invoicedate ON cleaned_transactions (InvoiceDate);
CREATE INDEX idx_invoice     ON cleaned_transactions (Invoice);

-- --- Verifikasi hasil cleaning ---------------------------------------------
SELECT COUNT(*) FROM cleaned_transactions;                     -- target: 820.663

SHOW INDEX FROM cleaned_transactions;

-- Proporsi baris retur vs normal, dan dampaknya ke revenue
SELECT
    is_return,
    COUNT(*)          AS jumlah_baris,
    SUM(LineRevenue)  AS total_revenue
FROM cleaned_transactions
GROUP BY is_return;
-- target: is_return=0 -> 802.725 baris, 17.434.690,73
--         is_return=1 ->  17.938 baris,   -719.712,08

-- Pastikan StockCode administratif sudah hilang (targetnya: 0 baris)
SELECT DISTINCT StockCode
FROM cleaned_transactions
WHERE StockCode IN ('POST','D','C2','DOT','M','m','BANK CHARGES','CRUK','AMAZONFEE','S','B');

-- Net revenue keseluruhan (penjualan dikurangi retur)
SELECT SUM(LineRevenue) AS net_revenue FROM cleaned_transactions;   -- target: 16.714.978,65

SELECT * FROM cleaned_transactions LIMIT 10;


-- =====================================================
-- STEP 3 : COHORT ANALYSIS
-- =====================================================
-- cohort_month  : bulan pembelian PERTAMA customer (dihitung dari transaksi
--                 non-retur saja, supaya cohort tidak salah ter-set oleh
--                 baris retur yang kebetulan urutannya lebih awal)
-- activity_month: bulan aktivitas (termasuk retur, supaya net_revenue tetap akurat)
-- cohort_index  : jarak bulan sejak cohort_month (0 = bulan pertama bergabung)
--
-- Catatan: baris dengan cohort_index < 0 (aktivitas tercatat SEBELUM
-- cohort_month, biasanya retur tanpa pembelian asli yang valid di data ini)
-- adalah anomali dan di-exclude dengan filter WHERE.
-- >>> JALANKAN VIA COMMAND LINE (mysql -u root -p), bukan Workbench <

DROP TABLE IF EXISTS cohort_analysis;

CREATE TABLE cohort_analysis AS
WITH customer_first_purchase AS (
    SELECT
        CustomerID,
        DATE_FORMAT(MIN(InvoiceDate), '%Y-%m-01') AS cohort_month
    FROM cleaned_transactions
    WHERE is_return = 0
    GROUP BY CustomerID
),
monthly_activities AS (
    SELECT
        CustomerID,
        DATE_FORMAT(InvoiceDate, '%Y-%m-01') AS activity_month,
        SUM(LineRevenue) AS monthly_revenue
    FROM cleaned_transactions
    GROUP BY CustomerID, activity_month
),
joined AS (
    SELECT
        m.CustomerID,
        c.cohort_month,
        m.activity_month,
        m.monthly_revenue,
        PERIOD_DIFF(
            DATE_FORMAT(m.activity_month, '%Y%m'),
            DATE_FORMAT(c.cohort_month, '%Y%m')
        ) AS cohort_index
    FROM monthly_activities m
    JOIN customer_first_purchase c
        ON m.CustomerID = c.CustomerID
)
SELECT *
FROM joined
WHERE cohort_index >= 0   -- exclude anomali: aktivitas sebelum cohort_month
ORDER BY cohort_month, cohort_index;

-- --- Verifikasi cohort_analysis --------------------------------------------
SELECT COUNT(*) AS total_baris_cohort FROM cohort_analysis;     -- target: 26.679

SELECT COUNT(*) AS anomali_negatif
FROM cohort_analysis
WHERE cohort_index < 0;
-- Targetnya: 0 (sudah difilter di query pembentukan tabel)

SELECT * FROM cohort_analysis LIMIT 20;

-- Preview jumlah customer aktif per cohort_index (bentuk awal retention table)
SELECT cohort_month, cohort_index, COUNT(DISTINCT CustomerID) AS jumlah_customer_aktif
FROM cohort_analysis
GROUP BY cohort_month, cohort_index
ORDER BY cohort_month, cohort_index
LIMIT 30;


-- =====================================================
-- STEP 4 : RETENTION RATE PER COHORT
-- =====================================================
-- retention_rate_pct = (customer aktif di cohort_index ke-N) / (customer awal cohort_index = 0)
-- Tabel ini yang langsung dipakai sebagai source untuk heatmap retensi di dashboard.

DROP TABLE IF EXISTS cohort_retention_rate;

CREATE TABLE cohort_retention_rate AS
WITH cohort_size AS (
    SELECT cohort_month, COUNT(DISTINCT CustomerID) AS initial_customers
    FROM cohort_analysis
    WHERE cohort_index = 0
    GROUP BY cohort_month
),
cohort_counts AS (
    SELECT cohort_month, cohort_index, COUNT(DISTINCT CustomerID) AS active_customers
    FROM cohort_analysis
    GROUP BY cohort_month, cohort_index
)
SELECT
    cc.cohort_month,
    cc.cohort_index,
    cc.active_customers,
    cs.initial_customers,
    ROUND(cc.active_customers * 100.0 / cs.initial_customers, 2) AS retention_rate_pct
FROM cohort_counts cc
JOIN cohort_size cs ON cc.cohort_month = cs.cohort_month
ORDER BY cc.cohort_month, cc.cohort_index;

-- --- Verifikasi cohort_retention_rate ---------------------------------------
SELECT COUNT(*) AS total_baris_retention FROM cohort_retention_rate;   -- target: 325

SELECT * FROM cohort_retention_rate
WHERE cohort_month = '2009-12-01'
ORDER BY cohort_index;

-- Validasi logika: retention_rate_pct di cohort_index = 0 harus selalu 100%
SELECT DISTINCT retention_rate_pct
FROM cohort_retention_rate
WHERE cohort_index = 0;
-- Targetnya: hanya muncul nilai 100.00


-- =====================================================
-- STEP 5 : VIEW & EXPORT UNTUK TAHAP PYTHON (RFM & K-MEANS)
-- =====================================================
-- View ini dipakai sebagai sumber RFM di Python. CustomerID, InvoiceDate,
-- LineRevenue, dan Invoice sudah bersih (exclude admin code & null customer);
-- is_return tetap disertakan agar Python bisa pilih mau exclude retur atau
-- tidak saat menghitung Frequency/Monetary.

CREATE OR REPLACE VIEW vw_rfm_source AS
SELECT
    CustomerID,
    Invoice,
    InvoiceDate,
    Quantity,
    Price,
    LineRevenue,
    is_return,
    Country
FROM cleaned_transactions;

-- =====================================================
-- EKSPOR KE CSV (jalankan dari Command Prompt/PowerShell,
-- BUKAN dari dalam sesi mysql>, dan keluar dulu pakai 'exit;')
-- =====================================================
-- mysql -u root -p retail_b2b -e "SELECT * FROM cleaned_transactions" --batch --silent > "D:/b2b-cohort-clv-optimization/cleaned_transactions.csv"
-- mysql -u root -p retail_b2b -e "SELECT * FROM cohort_analysis" --batch --silent > "D:/b2b-cohort-clv-optimization/cohort_data.csv"
-- mysql -u root -p retail_b2b -e "SELECT * FROM cohort_retention_rate" --batch --silent > "D:/b2b-cohort-clv-optimization/cohort_retention_rate.csv"