# =====================================================
# PROJECT  : Analisis Kohort & Pemodelan CLV untuk Optimasi Peluncuran Produk B2B
# STAGE    : Enrichment RFM Segments untuk BI Tools (Power BI & Tableau)
# INPUT    : outputs/rfm_segments.csv  (hasil RFM + K-Means sebelumnya)
# OUTPUT   : outputs/rfm_segments_enriched.csv
#
# TUJUAN:
#   Memindahkan semua "calculated field" yang sebelumnya direncanakan dibuat
#   manual di Tableau (LOD expressions) / Power BI (DAX measures) menjadi
#   kolom yang sudah jadi di sini. Alasannya:
#     1. Satu sumber kebenaran (single source of truth) -- logika bisnis
#        cukup didefinisikan sekali di Python, tidak terduplikasi &
#        berisiko beda hasil antara versi Power BI vs Tableau.
#     2. Tableau Public / Power BI tinggal drag kolom, tidak perlu lagi
#        menulis FIXED LOD atau DAX measure manual.
#
# KOLOM BARU YANG DITAMBAHKAN:
#   NetRevenueAll     -> setara Tableau: { FIXED : SUM([Monetary]) }
#   RevenueSharePct   -> setara Tableau: SUM([Monetary]) / TOTAL(SUM([Monetary]))
#   AvgPerCustomer    -> setara Tableau: { FIXED [Segment] : SUM/COUNTD }
#   RiskHighlight     -> setara Tableau: IF [ReturnRate] > 0.15 THEN ... END
#   PriorityTier      -> tier prioritas (qcut Monetary per Segment)
#   FullScale         -> konstanta 100, untuk teknik "bar-in-bar" di Tableau
#                        / track 100% di Power BI -- tidak perlu calculated
#                        field terpisah lagi di tools BI manapun
# =====================================================

import pandas as pd
import numpy as np

INPUT_PATH = 'outputs/rfm_segments.csv'
OUTPUT_PATH = 'outputs/rfm_segments_enriched.csv'


def compute_priority_tier(df: pd.DataFrame, value_col: str = 'Monetary',
                           group_col: str = 'Segment') -> pd.Series:
    """
    Bagi tiap segmen jadi 3 tier prioritas berdasarkan kuantil Monetary
    DI DALAM segmennya masing-masing (bukan kuantil global), supaya
    perbandingan tier tetap relevan meski antar-segmen skalanya jauh beda.

    Kalau jumlah nilai unik di suatu segmen kurang dari 3, otomatis semua
    baris di segmen itu diberi 'Tier 1 (Prioritas Utama)' -- menghindari
    error qcut yang butuh minimal 3 bin berbeda.
    """
    result = pd.Series(index=df.index, dtype='object')
    tier_labels = ['Tier 3', 'Tier 2', 'Tier 1 (Prioritas Utama)']

    for _, group in df.groupby(group_col):
        if group[value_col].nunique() >= 3:
            tiers = pd.qcut(group[value_col], q=3, labels=tier_labels)
            result.loc[group.index] = tiers.astype(str)
        else:
            result.loc[group.index] = tier_labels[-1]

    return result


def enrich_rfm_segments(rfm: pd.DataFrame) -> pd.DataFrame:
    rfm = rfm.copy()

    # --- 1. NetRevenueAll: total revenue seluruh customer (konstan di semua baris) ---
    rfm['NetRevenueAll'] = rfm['Monetary'].sum()

    # --- 2. Agregasi per segmen: total revenue & jumlah customer unik -------------
    segment_agg = (
        rfm.groupby('Segment')
        .agg(
            SegmentRevenue=('Monetary', 'sum'),
            SegmentCustomerCount=('CustomerID', 'nunique'),
        )
        .reset_index()
    )

    # --- 3. RevenueSharePct: kontribusi % segmen terhadap total revenue ----------
    segment_agg['RevenueSharePct'] = (
        segment_agg['SegmentRevenue'] / rfm['Monetary'].sum() * 100
    ).round(1)

    # --- 4. AvgPerCustomer: rata-rata revenue per customer DALAM segmen itu -------
    segment_agg['AvgPerCustomer'] = (
        segment_agg['SegmentRevenue'] / segment_agg['SegmentCustomerCount']
    ).round(2)

    # Gabungkan hasil agregasi balik ke tiap baris customer
    rfm = rfm.merge(
        segment_agg[['Segment', 'RevenueSharePct', 'AvgPerCustomer']],
        on='Segment', how='left'
    )

    # --- 5. RiskHighlight: flag per customer untuk return rate tinggi -------------
    rfm['RiskHighlight'] = np.where(rfm['ReturnRate'] > 0.15, 'Risiko Tinggi', 'Normal')

    # --- 6. PriorityTier: tier prioritas per segmen --------------------------------
    rfm['PriorityTier'] = compute_priority_tier(rfm)

    # --- 7. FullScale: konstanta 100, dipakai langsung untuk teknik bar-in-bar ----
    rfm['FullScale'] = 100

    return rfm


if __name__ == '__main__':
    rfm_segments = pd.read_csv(INPUT_PATH)
    print(f"Baris dimuat dari {INPUT_PATH}: {len(rfm_segments):,}")
    print("Kolom asli:", list(rfm_segments.columns))

    enriched = enrich_rfm_segments(rfm_segments)

    print("\nKolom setelah enrichment:", list(enriched.columns))
    print("\nContoh hasil agregasi per segmen:")
    print(
        enriched.groupby('Segment')[
            ['RevenueSharePct', 'AvgPerCustomer']
        ].first()
    )
    print("\nDistribusi PriorityTier per segmen:")
    print(enriched.groupby(['Segment', 'PriorityTier']).size())
    print("\nDistribusi RiskHighlight:")
    print(enriched['RiskHighlight'].value_counts())

    enriched.to_csv(OUTPUT_PATH, index=False)
    print(f"\nTersimpan ke: {OUTPUT_PATH}")





    