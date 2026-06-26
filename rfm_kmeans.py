# =====================================================
# PROJECT  : Analisis Kohort & Pemodelan CLV untuk Optimasi Peluncuran Produk B2B
# STAGE    : RFM Engineering + K-Means Clustering (Segmentasi Klien B2B)
# INPUT    : data/cleaned_transactions.csv (hasil export dari tabel cleaned_transactions di SQL)
# OUTPUT   : outputs/rfm_segments.csv (siap dipakai di dashboard / Step 4 actionable list)
# =====================================================

import pandas as pd
import numpy as np
import datetime as dt
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

sns.set_style("whitegrid")

# -----------------------------------------------------
# 1. MEMUAT DATA
# -----------------------------------------------------
# Kolom yang tersedia: CustomerID, Invoice, InvoiceDate, Quantity, Price,
#                      LineRevenue, is_return, Country
#
# Catatan format: hasil export dari MySQL Workbench ternyata UTF-16 dengan
# TAB sebagai pemisah kolom (bukan koma) dan TANPA header di baris pertama,
# meski ekstensinya .csv. Nama kolom diberikan manual lewat `names=`.

column_names = ['Invoice', 'StockCode', 'Description', 'Quantity', 'InvoiceDate',
                 'Price', 'CustomerID', 'Country', 'is_return', 'LineRevenue']
df = pd.read_csv('data/cleaned_transactions.csv', encoding='utf-16', sep='\t',
                  header=None, names=column_names)

df['InvoiceDate'] = pd.to_datetime(df['InvoiceDate'])


print(f"Total baris  : {len(df):,}")
print(f"Total klien  : {df['CustomerID'].nunique():,}")
print(f"Periode data : {df['InvoiceDate'].min().date()} s.d. {df['InvoiceDate'].max().date()}")


# -----------------------------------------------------
# 2. REKAYASA FITUR RFM (+ RETURN RATE sebagai fitur pelengkap)
# -----------------------------------------------------
# Keputusan bisnis untuk proyek ini:
#   - Recency  : dihitung dari SEMUA transaksi (jual & retur)
#   - Frequency: HANYA dari invoice non-retur (retur bukan sinyal loyalitas)
#   - Monetary : NET revenue (penjualan dikurangi retur)
#   - ReturnRate: fitur tambahan untuk menangkap klien bermasalah

snapshot_date = df['InvoiceDate'].max() + dt.timedelta(days=1)

recency_df = (
    df.groupby('CustomerID')['InvoiceDate']
    .max()
    .reset_index()
    .rename(columns={'InvoiceDate': 'LastPurchaseDate'})
)
recency_df['Recency'] = (snapshot_date - recency_df['LastPurchaseDate']).dt.days

frequency_df = (
    df[df['is_return'] == 0]
    .groupby('CustomerID')['Invoice']
    .nunique()
    .reset_index()
    .rename(columns={'Invoice': 'Frequency'})
)

monetary_df = (
    df.groupby('CustomerID')['LineRevenue']
    .sum()
    .reset_index()
    .rename(columns={'LineRevenue': 'Monetary'})
)

return_rate_df = (
    df.groupby('CustomerID')['is_return']
    .agg(total_invoice_lines='count', total_return_lines='sum')
    .reset_index()
)
return_rate_df['ReturnRate'] = (
    return_rate_df['total_return_lines'] / return_rate_df['total_invoice_lines']
)

rfm = (
    recency_df[['CustomerID', 'Recency']]
    .merge(frequency_df, on='CustomerID', how='left')
    .merge(monetary_df, on='CustomerID', how='left')
    .merge(return_rate_df[['CustomerID', 'ReturnRate']], on='CustomerID', how='left')
)

# Klien yang seluruh transaksinya retur tidak akan punya Frequency -> NaN.
# Ini klien bermasalah, bukan klien hilang, jadi diisi 0 (bukan di-drop).
rfm['Frequency'] = rfm['Frequency'].fillna(0)

# Bersihkan floating-point noise: klien yang penjualan & retur-nya saling
# meniadakan secara matematis seharusnya Monetary = 0 persis, tapi karena
# presisi desimal komputer, hasilnya kadang berupa angka residu sangat kecil
# (misal 1.4e-14) bukan 0 bulat. Tanpa pembersihan ini, nilai tersebut akan
# meledak secara visual saat di-log-transform untuk plotting.
rfm['Monetary'] = rfm['Monetary'].where(rfm['Monetary'].abs() > 1e-6, 0)

print("\nRingkasan RFM sebelum clustering:")
print(rfm.describe().round(2))


# -----------------------------------------------------
# 3. PENANGANAN OUTLIER & NORMALISASI
# -----------------------------------------------------
# Log-transform sebelum scaling, karena RFM B2B grosir biasanya sangat skewed.
rfm_log = rfm.copy()
rfm_log['Monetary_log'] = np.sign(rfm['Monetary']) * np.log1p(np.abs(rfm['Monetary']))
rfm_log['Frequency_log'] = np.log1p(rfm['Frequency'])
rfm_log['Recency_log'] = np.log1p(rfm['Recency'])

features = ['Recency_log', 'Frequency_log', 'Monetary_log', 'ReturnRate']
X = rfm_log[features]

scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)


# -----------------------------------------------------
# 4. MENENTUKAN JUMLAH CLUSTER OPTIMAL (ELBOW METHOD + SILHOUETTE)
# -----------------------------------------------------
inertia_list = []
silhouette_list = []
k_range = range(2, 9)

for k in k_range:
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(X_scaled)
    inertia_list.append(km.inertia_)
    silhouette_list.append(silhouette_score(X_scaled, labels))

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

axes[0].plot(list(k_range), inertia_list, marker='o')
axes[0].set_title('Elbow Method', fontsize=13, fontweight='bold')
axes[0].set_xlabel('Jumlah Cluster (k)')
axes[0].set_ylabel('Inertia (WCSS)')
axes[0].grid(True, linestyle='--', alpha=0.5)

axes[1].plot(list(k_range), silhouette_list, marker='o', color='darkorange')
axes[1].set_title('Silhouette Score', fontsize=13, fontweight='bold')
axes[1].set_xlabel('Jumlah Cluster (k)')
axes[1].set_ylabel('Silhouette Score')
axes[1].grid(True, linestyle='--', alpha=0.5)

sns.despine()
plt.tight_layout()
plt.savefig('outputs/elbow_silhouette_evaluation.png', dpi=150)
plt.show()

print("\nInertia per k:", dict(zip(k_range, np.round(inertia_list, 1))))
print("Silhouette per k:", dict(zip(k_range, np.round(silhouette_list, 3))))
print("\n>> Tentukan k final berdasarkan titik 'siku' (elbow) DAN silhouette score tertinggi.")
print(">> Ganti nilai K_FINAL di bawah sesuai hasil evaluasi ini.")


# -----------------------------------------------------
# 5. K-MEANS CLUSTERING (FINAL)
# -----------------------------------------------------
K_FINAL = 3  # <-- Untuk dataset ini, silhouette score tertinggi ada di k=3
             #     (0.408), lebih tinggi dari k=4 (0.317). Elbow tidak
             #     menunjukkan siku tajam, jadi silhouette jadi acuan utama.
             #     Selalu cek ulang plot saat dataset berubah.

kmeans = KMeans(n_clusters=K_FINAL, random_state=42, n_init=10)
rfm['Cluster'] = kmeans.fit_predict(X_scaled)


# -----------------------------------------------------
# 6. VALIDASI & PELABELAN SEGMEN BISNIS (TANPA HARDCODE INDEX)
# -----------------------------------------------------
# PENTING: index cluster dari K-Means (0,1,2,...) TIDAK punya urutan makna
# bisnis tetap -- bisa berubah setiap kali model di-fit ulang. Label bisnis
# ditentukan SETELAH melihat karakteristik rata-rata tiap cluster relatif
# terhadap median SELURUH cluster -- bukan rank absolut yang kaku, supaya
# tidak mudah "jatuh" ke kategori default saja.

cluster_profile = rfm.groupby('Cluster')[['Recency', 'Frequency', 'Monetary', 'ReturnRate']].mean().round(2)
cluster_profile['JumlahKlien'] = rfm['Cluster'].value_counts()
print("\nProfil rata-rata tiap cluster (gunakan ini untuk menentukan label bisnis):")
print(cluster_profile.sort_values('Monetary', ascending=False))

# PENTING: median dihitung dari SELURUH POPULASI KLIEN (rfm), bukan dari
# rata-rata antar-cluster (cluster_profile). Dengan k kecil (3-4 cluster),
# median antar-cluster terlalu mudah jatuh tepat di salah satu cluster itu
# sendiri, sehingga cluster tersebut "menabrak" mediannya sendiri dan salah
# diklasifikasikan. Median populasi jauh lebih stabil sebagai garis pembanding.
med_recency = rfm['Recency'].median()
med_frequency = rfm['Frequency'].median()
med_monetary = rfm['Monetary'].median()

def classify_cluster(row):
    """
    Klasifikasi tiap CLUSTER (bukan tiap baris klien) berdasarkan posisi
    rata-ratanya relatif terhadap median SELURUH POPULASI klien.
      - Loyal/Champions : Monetary & Frequency >= median, Recency <= median
      - At Risk         : Monetary >= median TAPI Recency > median (lama tidak beli)
      - New Potential   : Recency <= median TAPI Monetary & Frequency < median (baru bergabung)
      - Sleeping Dogs   : sisanya, atau ReturnRate >= 20% (klien bermasalah)
    """
    high_monetary = row['Monetary'] >= med_monetary
    high_frequency = row['Frequency'] >= med_frequency
    low_recency = row['Recency'] <= med_recency
    high_return = row['ReturnRate'] >= 0.20

    if high_return:
        return 'Sleeping Dogs'
    elif high_monetary and high_frequency and low_recency:
        return 'Loyal/Champions'
    elif high_monetary and not low_recency:
        return 'At Risk'
    elif not high_monetary and not high_frequency and low_recency:
        return 'New Potential'
    else:
        return 'Sleeping Dogs'

cluster_profile['Segment'] = cluster_profile.apply(classify_cluster, axis=1)
print("\nMapping Cluster -> Segment:")
print(cluster_profile[['Recency', 'Frequency', 'Monetary', 'ReturnRate', 'Segment']])

segment_map = cluster_profile['Segment'].to_dict()
rfm['Segment'] = rfm['Cluster'].map(segment_map)

print("\nJumlah klien per segmen bisnis (hasil akhir):")
print(rfm['Segment'].value_counts())

print("\nKontribusi revenue per segmen:")
revenue_share = (
    rfm.groupby('Segment')['Monetary'].sum()
    .div(rfm['Monetary'].sum())
    .mul(100)
    .round(1)
    .sort_values(ascending=False)
)
print(revenue_share.astype(str) + '%')


# -----------------------------------------------------
# 7. VISUALISASI HASIL CLUSTERING
# -----------------------------------------------------
plt.figure(figsize=(10, 6))
plot_df = rfm[rfm['Monetary'] > 0].copy()  # log-scale tidak bisa plot nilai <= 0
sns.scatterplot(
    data=plot_df, x='Frequency', y='Monetary', hue='Segment',
    palette='viridis', alpha=0.7
)
plt.title('Segmentasi Klien B2B Berbasis Algoritma K-Means', fontsize=14, fontweight='bold')
plt.xlabel('Frekuensi Transaksi (Log)', fontsize=12)
plt.ylabel('Total Nilai Transaksi / Monetary (Log)', fontsize=12)
plt.yscale('log')
plt.xscale('log')
plt.grid(True, linestyle='--', alpha=0.5)
sns.despine()
plt.tight_layout()
plt.savefig('outputs/rfm_segmentation_scatter.png', dpi=150)
plt.show()


# -----------------------------------------------------
# 8. EXPORT HASIL UNTUK DASHBOARD & SALES TEAM
# -----------------------------------------------------
rfm_export = rfm[['CustomerID', 'Recency', 'Frequency', 'Monetary', 'ReturnRate', 'Cluster', 'Segment']]
rfm_export.to_csv('outputs/rfm_segments.csv', index=False)
print("\nFile 'outputs/rfm_segments.csv' berhasil dibuat -- siap dipakai di dashboard / actionable list Sales.")














