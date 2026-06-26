# Analisis Kohort & Pemodelan Customer Lifetime Value (CLV) untuk Optimasi Peluncuran Produk B2B

> Segmentasi pelanggan berbasis Machine Learning (K-Means) dan analisis retensi kohort untuk menentukan target pasar paling tepat bagi lini produk premium B2B yang akan diluncurkan.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![MySQL](https://img.shields.io/badge/MySQL-8.0-orange)
![Status](https://img.shields.io/badge/status-completed-brightgreen)

---

## 📌 Latar Belakang Bisnis

Tim Product Development berencana merilis lini produk premium, namun meluncurkannya ke pelanggan yang salah akan membuang biaya promosi. Proyek ini menjawab pertanyaan:

> **Pelanggan B2B mana yang paling layak menjadi target awal ("early access") untuk produk premium baru, berdasarkan perilaku belanja historis mereka?**

**Dataset:** [Online Retail II](https://archive.ics.uci.edu/dataset/502/online+retail+ii) (UCI Machine Learning Repository) — 1+ juta transaksi dari perusahaan retail online yang menjual produk suvenir grosir ke pelanggan wholesaler/B2B, periode Des 2009 – Des 2011.

---

## 🖼️ Preview Dashboard
![Dashboard Preview](<images/dashboard-overview-1.png>) 
![Dashboard Preview](<images/dashboard-overview-2.png>)

---

## 📊 Visualisasi Interaktif (Alternatif)

Selain dashboard Plotly Dash, analisis ini juga divisualisasikan di Power BI dan Tableau Public — bisa diakses langsung tanpa perlu clone repo atau install apa pun:

- 📈 **Power BI:** [Lihat Dashboard](https://app.powerbi.com/links/tPN5yMDT9k?ctid=8b603e04-2c81-4b3c-a54e-b1211ffbceed&pbi_source=linkShare)
- 📊 **Tableau Public:** [Lihat Dashboard](https://public.tableau.com/app/profile/yusuf.jamil/viz/DashboardAnalisisKohortPemodelanCustomerLifetimeValueCLVuntukOptimasiPeluncuranProdukB2B/Dashboard2)

---

## 🛠️ Tech Stack

| Tahap | Tools |
|---|---|
| Database & ETL | MySQL 8.0, SQL (Window Functions, CTE) |
| Data Cleaning & Feature Engineering | Python (pandas) |
| Machine Learning | scikit-learn (K-Means Clustering) |
| Dashboard Interaktif | Plotly Dash |
| Visualisasi Alternatif | Power BI, Tableau Public |

---

## 📂 Struktur Proyek

```
b2b-cohort-clv-optimization/
│
├── sql/                          # Script SQL: import, cleaning, cohort analysis
│   └── pipeline.sql
├── rfm_kmeans.py                 # RFM feature engineering + K-Means clustering
├── rfm_enrichment_export.py      # Enrichment kolom untuk Power BI/Tableau
├── dashboard.py                  # Dashboard interaktif (Plotly Dash)
├── outputs/                      # Hasil export (CSV, model) -- tidak di-commit, lihat .gitignore
├── images/                       # Screenshot dashboard untuk README
├── requirements.txt
└── README.md
```

---

## 🚀 Cara Menjalankan

### 1. Clone repo & setup environment
```bash
git clone https://github.com/<GalFoks>/b2b-cohort-clv-optimization.git
cd b2b-cohort-clv-optimization
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

### 2. Download dataset
Dataset asli tidak disertakan di repo (ukurannya besar). Download dari [UCI ML Repository](https://archive.ics.uci.edu/dataset/502/online+retail+ii), simpan sebagai `data/online_retail_II.csv`.

### 3. Jalankan pipeline SQL

> ⚠️ **Catatan:** langkah ini dijalankan di **MySQL**, bukan di Python/VS Code. Pastikan MySQL Server 8.0 sudah terinstall dan berjalan di komputer kamu.

**a. Buat database baru** (lewat MySQL Workbench atau command line):
```sql
CREATE DATABASE retail_b2b;
```

**b. Import dataset mentah** ke dalam database tersebut sebagai tabel (misalnya `raw_transactions`), menggunakan fitur **Table Data Import Wizard** di MySQL Workbench, atau lewat command line `LOAD DATA INFILE`.

**c. Jalankan `sql/pipeline.sql`** untuk membentuk tabel hasil olahan: `cleaned_transactions`, `cohort_analysis`, dan `cohort_retention_rate`.

- **Lewat MySQL Workbench:** buka file `sql/pipeline.sql` (File → Open SQL Script), pilih database `retail_b2b` sebagai schema aktif, lalu klik tombol ⚡ **Execute** (atau tekan `Ctrl+Shift+Enter`).
- **Lewat command line:**
```bash
  mysql -u root -p retail_b2b < sql/pipeline.sql
```

Lihat instruksi detail di dalam file SQL tersebut.
### 4. Jalankan RFM + K-Means
```bash
python rfm_kmeans.py
python rfm_enrichment_export.py
```

### 5. Jalankan dashboard
```bash
python dashboard.py
```
Buka browser ke `http://127.0.0.1:8050`

---

## 📊 Metodologi

1. **Data Cleaning (SQL)** — exclude transaksi tanpa `CustomerID`, biaya administratif (ongkos kirim, biaya bank), dan catatan internal yang menyamar sebagai data produk. Transaksi return tetap disimpan dengan flag `is_return` untuk menghitung *net revenue* yang akurat.
2. **Cohort Analysis (SQL Window Functions)** — melacak bulan akuisisi pertama tiap pelanggan dan menghitung retention rate bulan-ke-bulan.
3. **RFM Feature Engineering (Python)** — menghitung Recency, Frequency, Monetary per pelanggan.
4. **K-Means Clustering** — segmentasi pelanggan berbasis perilaku belanja, jumlah cluster ditentukan lewat Silhouette Score (bukan tebakan manual).
5. **Dashboard** — visualisasi retensi kohort (heatmap), kontribusi revenue per segmen, dan actionable list klien prioritas untuk tim Sales.

---

## 💡 Insight Utama

- Segmen **Loyal/Champions** hanya berjumlah 39,2% dari total pelanggan, namun menyumbang **86,78%** dari total net revenue — menunjukkan konsentrasi nilai yang sangat tajam pada sebagian kecil klien.
- Perbedaan perilaku antar segmen sangat kontras: Loyal/Champions rata-rata bertransaksi 12,6x dengan recency 44,6 hari, sementara Sleeping Dogs rata-rata hanya 2,1x transaksi dan sudah tidak aktif selama hampir 300 hari.
- Retensi kohort turun tajam dari 100% di bulan ke-0 menjadi sekitar 25% di bulan ke-1, melandai ke titik terendah ~16% di sekitar bulan ke-9–10, lalu naik kembali secara bertahap menuju bulan ke-12 dan **memuncak di bulan ke-23 (25,06%)** — mengindikasikan siklus reorder tahunan (~12 dan ~24 bulan) yang khas pada bisnis wholesale B2B.
- Proses clustering mengidentifikasi sub-kelompok kecil (55 pelanggan) dengan rata-rata *return rate* 72% dan net revenue negatif — sinyal pelanggan bermasalah yang perlu ditinjau ulang, bukan target ekspansi produk.
- 220 pelanggan teridentifikasi sebagai "Risiko Tinggi" (return rate rata-rata 35,2%, vs 1,6% pada pelanggan normal) — perlu pengecekan kualitas produk/proses sebelum diberi akses produk premium baru.
- **Rekomendasi:** lini produk premium dirilis sebagai program *early access* eksklusif untuk 1.959 klien Tier 1 (33% dari total pelanggan), yang secara historis berkontribusi 77,3% dari total revenue. Waktu peluncuran sebaiknya disinkronkan dengan siklus reorder tahunan untuk memaksimalkan adopsi awal.

---

## 📄 Lisensi

Dataset bersumber dari UCI Machine Learning Repository (domain publik untuk riset). Kode pada repo ini dirilis di bawah [MIT License](LICENSE).

---

## 👤 Kontak

**Muhammad Yusuf Jamil** — [LinkedIn](https://www.linkedin.com/in/muhammad-yusuf-jamil-4b5345248/) · [Email](yusufjamil316@gmail.com)


