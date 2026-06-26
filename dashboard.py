# =====================================================
# PROJECT  : Analisis Kohort & Pemodelan CLV untuk Optimasi Peluncuran Produk B2B
# STAGE    : Step 3 - Dashboard Strategis (Plotly + Dash)
# INPUT    : data/cohort_retention_rate.csv, outputs/rfm_segments.csv
# OUTPUT   : Dashboard interaktif di browser (http://127.0.0.1:8050)
# =====================================================
#
# Cara menjalankan:
#   pip install dash plotly pandas --break-system-packages
#   python dashboard.py
# lalu buka browser ke http://127.0.0.1:8050
#
# Layout dashboard:
#   - Atas   : KPI summary cards (Net Revenue, Active Customers,
#              Champions Count, Champions Revenue Share)
#   - Tengah : Heatmap retensi kohort (cohort_month x cohort_index)
#   - Kanan  : Bar chart kontribusi revenue per segmen
#   - Bawah  : Tabel actionable list klien "Loyal/Champions" untuk tim Sales

import pandas as pd
import plotly.graph_objects as go
from dash import Dash, dcc, html, dash_table
from dash.dash_table.Format import Format, Group, Scheme, Symbol

# =====================================================
# 0. DESIGN TOKENS
# =====================================================
# Palet "ledger" untuk analitik B2B wholesale: navy gelap sebagai warna
# kepercayaan/otoritas, amber sebagai aksen "premium" (mengacu pada lini
# produk premium yang akan diluncurkan), teal sebagai sinyal positif.
COLORS = {
    'bg':          '#F5F6FA',  # latar utama, abu kebiruan sangat lembut
    'surface':     '#FFFFFF',  # latar card/panel
    'navy':        '#16213E',  # warna utama: header, teks penting, KPI besar
    'navy_soft':   '#3D4A73',  # navy yang lebih lembut untuk elemen sekunder
    'amber':       '#D9A23B',  # aksen "premium" - Champions, highlight utama
    'amber_soft':  '#F1DDB0',
    'teal':        '#2F6F63',  # sinyal positif (retensi tinggi, growth)
    'slate':       '#A9AFC0',  # elemen netral/inaktif
    'text':        '#1F2533',
    'text_muted':  '#6B7280',
    'border':      '#E3E6ED',
}

FONT_DISPLAY = "'Sora', sans-serif"      # judul, angka KPI besar
FONT_BODY    = "'Inter', sans-serif"     # body text, label
FONT_MONO    = "'IBM Plex Mono', monospace"  # angka tabel, eyebrow label

# Warna tetap per segmen, supaya konsisten di seluruh dashboard
SEGMENT_COLOR_MAP = {
    'Loyal/Champions': COLORS['amber'],
    'New Potential':   COLORS['teal'],
    'At Risk':         COLORS['navy_soft'],
    'Sleeping Dogs':   COLORS['slate'],
}


# =====================================================
# 1. MEMUAT DATA
# =====================================================
def load_csv_flexible(path, expected_columns):
    """
    Membaca CSV hasil export MySQL Workbench, yang berdasarkan pengalaman
    di proyek ini SELALU dalam format: encoding UTF-16, separator TAB,
    dan TANPA header (baris pertama adalah data, bukan nama kolom).
    Nama kolom diberikan manual lewat `expected_columns`.

    Fallback ke UTF-8 + koma + ada header disediakan untuk jaga-jaga jika
    suatu saat file diekspor ulang dengan opsi "Include column names"
    tercentang di Workbench.
    """
    try:
        return pd.read_csv(path, encoding='utf-16', sep='\t',
                            header=None, names=expected_columns)
    except (UnicodeDecodeError, ValueError):
        return pd.read_csv(path, encoding='utf-8', sep=',')


cohort_cols = ['cohort_month', 'cohort_index', 'active_customers',
               'initial_customers', 'retention_rate_pct']
cohort_retention = load_csv_flexible('data/cohort_retention_rate.csv', cohort_cols)

rfm_segments = pd.read_csv('outputs/rfm_segments.csv')  # hasil to_csv pandas, sudah UTF-8 standar

print(f"Cohort retention rows : {len(cohort_retention):,}")
print(f"RFM segments rows     : {len(rfm_segments):,}")
print("Kolom cohort_retention:", list(cohort_retention.columns))
print("Kolom rfm_segments    :", list(rfm_segments.columns))


# =====================================================
# 2. SIAPKAN DATA HEATMAP RETENSI
# =====================================================
cohort_retention['cohort_month'] = pd.to_datetime(cohort_retention['cohort_month']).dt.strftime('%Y-%m')

heatmap_pivot = cohort_retention.pivot(
    index='cohort_month',
    columns='cohort_index',
    values='retention_rate_pct'
).sort_index()

# Colorscale sekuensial satu-hue (navy), bukan rainbow generik -- lebih
# tenang dibaca dan konsisten dengan identitas warna dashboard ini.
navy_scale = [
    [0.0, '#FFFFFF'],
    [0.15, '#E7EAF3'],
    [0.4, '#9AA6C9'],
    [0.7, '#4E5D94'],
    [1.0, COLORS['navy']],
]

fig_heatmap = go.Figure(data=go.Heatmap(
    z=heatmap_pivot.values,
    x=[f"Bulan ke-{i}" for i in heatmap_pivot.columns],
    y=heatmap_pivot.index,
    colorscale=navy_scale,
    colorbar=dict(
        title=dict(text='Retensi (%)', font=dict(family=FONT_BODY, size=12, color=COLORS['text_muted'])),
        tickfont=dict(family=FONT_MONO, size=11, color=COLORS['text_muted']),
        outlinewidth=0,
    ),
    hovertemplate='Cohort: %{y}<br>%{x}<br>Retensi: %{z:.1f}%<extra></extra>',
    zmin=0, zmax=100,
    xgap=3, ygap=3,
))
fig_heatmap.update_layout(
    title=dict(
        text='Retention Rate per Cohort Bulanan',
        font=dict(family=FONT_DISPLAY, size=18, color=COLORS['navy']),
        x=0.02, xanchor='left',
    ),
    xaxis_title=None,
    yaxis_title=None,
    font=dict(family=FONT_BODY, color=COLORS['text']),
    plot_bgcolor=COLORS['surface'],
    paper_bgcolor=COLORS['surface'],
    margin=dict(l=10, r=10, t=60, b=10),
    height=520,
)
fig_heatmap.update_yaxes(autorange='reversed', tickfont=dict(family=FONT_MONO, size=11))
fig_heatmap.update_xaxes(tickfont=dict(family=FONT_MONO, size=11))


# =====================================================
# 3. SIAPKAN DATA BAR CHART KONTRIBUSI REVENUE PER SEGMEN
# =====================================================
def fmt_money_short(x):
    """Format angka jadi notasi singkat (£14.5M / £820K) supaya label tidak kepanjangan."""
    if abs(x) >= 1_000_000:
        return f"£{x / 1_000_000:.1f}M"
    if abs(x) >= 1_000:
        return f"£{x / 1_000:.0f}K"
    return f"£{x:,.0f}"


seg_customer_count = rfm_segments.groupby('Segment')['CustomerID'].count().reset_index(name='CustomerCount')

revenue_per_segment = (
    rfm_segments.groupby('Segment')['Monetary']
    .sum()
    .reset_index()
    .merge(seg_customer_count, on='Segment')
    .sort_values('Monetary', ascending=True)  # ascending agar bar terbesar di atas saat horizontal
)
revenue_per_segment['RevenueShare'] = (
    revenue_per_segment['Monetary'] / revenue_per_segment['Monetary'].sum() * 100
).round(1)
revenue_per_segment['AvgPerCustomer'] = (
    revenue_per_segment['Monetary'] / revenue_per_segment['CustomerCount']
)
revenue_per_segment['BarColor'] = revenue_per_segment['Segment'].map(
    lambda s: SEGMENT_COLOR_MAP.get(s, COLORS['slate'])
)

# Label informatif: persentase + nilai absolut + jumlah klien dalam satu baris,
# supaya pembaca tidak perlu menebak skala sebenarnya dari persentase saja.
revenue_per_segment['BarLabel'] = revenue_per_segment.apply(
    lambda r: f"{r['RevenueShare']}%   ·   {fmt_money_short(r['Monetary'])}   ·   {r['CustomerCount']:,} klien",
    axis=1
)
# Tick label dua baris: nama segmen (bold) + rata-rata revenue per klien sebagai subtitle.
revenue_per_segment['TickLabel'] = revenue_per_segment.apply(
    lambda r: f"<b>{r['Segment']}</b><br>avg {fmt_money_short(r['AvgPerCustomer'])}/klien",
    axis=1
)

total_net_revenue = revenue_per_segment['Monetary'].sum()
max_share = revenue_per_segment['RevenueShare'].max()

fig_bar = go.Figure()

# Trace 1: "track" abu-abu transparan sepanjang 100% -- memberi konteks skala
# proporsi (gaya progress-bar), supaya mata langsung tahu seberapa besar
# porsi tiap segmen relatif terhadap keseluruhan, bukan cuma relatif sesama bar.
fig_bar.add_trace(go.Bar(
    x=[100] * len(revenue_per_segment),
    y=revenue_per_segment['TickLabel'],
    orientation='h',
    marker_color=COLORS['bg'],
    marker_line_width=1,
    marker_line_color=COLORS['border'],
    hoverinfo='skip',
    showlegend=False,
))

# Trace 2: nilai aktual (persentase kontribusi revenue), warna sesuai segmen.
fig_bar.add_trace(go.Bar(
    x=revenue_per_segment['RevenueShare'],
    y=revenue_per_segment['TickLabel'],
    orientation='h',
    text=revenue_per_segment['BarLabel'],
    textposition='outside',
    textfont=dict(family=FONT_MONO, size=12.5, color=COLORS['text']),
    marker_color=revenue_per_segment['BarColor'],
    marker_line_width=0,
    customdata=revenue_per_segment[['Monetary', 'CustomerCount', 'AvgPerCustomer']],
    hovertemplate=(
        '<b>%{y}</b><br>'
        'Kontribusi: %{x}%<br>'
        'Total revenue: £%{customdata[0]:,.0f}<br>'
        'Jumlah klien: %{customdata[1]:,.0f}<br>'
        'Rata-rata/klien: £%{customdata[2]:,.0f}'
        '<extra></extra>'
    ),
    showlegend=False,
))

fig_bar.update_layout(
    barmode='overlay',
    title=dict(
        text='Kontribusi Revenue per Segmen Klien',
        font=dict(family=FONT_DISPLAY, size=18, color=COLORS['navy']),
        x=0.02, xanchor='left',
    ),
    annotations=[
        dict(
            text=f"Total Net Revenue: <b>{fmt_money_short(total_net_revenue)}</b>",
            font=dict(family=FONT_BODY, size=12, color=COLORS['text_muted']),
            xref='paper', yref='paper', x=0.02, y=1.085,
            showarrow=False, xanchor='left',
        )
    ],
    xaxis=dict(
        title=None, range=[0, max_share * 1.45],
        showgrid=True, gridcolor=COLORS['border'], zeroline=False,
        tickfont=dict(family=FONT_MONO, size=11, color=COLORS['text_muted']),
        ticksuffix='%',
    ),
    yaxis=dict(
        title=None, tickfont=dict(family=FONT_BODY, size=13, color=COLORS['text']),
        showgrid=False,
    ),
    font=dict(family=FONT_BODY, color=COLORS['text']),
    plot_bgcolor=COLORS['surface'],
    paper_bgcolor=COLORS['surface'],
    margin=dict(l=10, r=30, t=85, b=10),
    height=520,
    bargap=0.45,
)



# =====================================================
# 4. SIAPKAN ACTIONABLE LIST KLIEN "LOYAL/CHAMPIONS"
# =====================================================
champions_list = (
    rfm_segments[rfm_segments['Segment'] == 'Loyal/Champions']
    .sort_values('Monetary', ascending=False)
    .copy()
)
champions_list['Monetary'] = champions_list['Monetary'].round(2)
# ReturnRate TIDAK dikali 100 di sini -- dibiarkan dalam bentuk fraksi (0-1)
# karena dash_table.FormatTemplate.percentage() yang akan menanganinya nanti,
# supaya tampilan akhirnya konsisten dengan tanda '%' otomatis.

# --- Priority Tier: triase cepat tanpa perlu baca angka mentah ----------
# Dibagi 3 tier berdasarkan kuantil Monetary KHUSUS di dalam segmen
# Champions ini, supaya Sales tahu siapa yang harus dihubungi PALING duluan.
champions_list['PriorityTier'] = pd.qcut(
    champions_list['Monetary'], q=3,
    labels=['Tier 3', 'Tier 2', 'Tier 1 (Prioritas Utama)']
).astype(str)

# NOTE: dataset Online Retail II tidak memiliki kolom kontak (nama, email,
# telepon) -- proyek ini berbasis CustomerID anonim. Untuk kebutuhan nyata,
# kolom kontak harus di-join dari sistem CRM perusahaan menggunakan
# CustomerID sebagai key.
champions_table_cols = ['CustomerID', 'PriorityTier', 'Recency', 'Frequency', 'Monetary', 'ReturnRate']
champions_display = champions_list[champions_table_cols]


def data_bar_styles(df, column, color):
    """
    Membuat 'mini bar chart' di dalam sel tabel Dash, berbasis CSS
    linear-gradient -- supaya besar-kecilnya Monetary terlihat langsung
    tanpa perlu sorting manual atau membaca tiap angka satu per satu.
    """
    n_bins = 50
    col_min, col_max = df[column].min(), df[column].max()
    bounds = [i / n_bins for i in range(n_bins + 1)]
    ranges = [col_min + (col_max - col_min) * b for b in bounds]
    styles = []
    for i in range(1, len(bounds)):
        lo, hi = ranges[i - 1], ranges[i]
        pct = bounds[i] * 100
        query = f'{{{column}}} >= {lo}' + (f' && {{{column}}} < {hi}' if i < len(bounds) - 1 else '')
        styles.append({
            'if': {'filter_query': query, 'column_id': column},
            'background': (
                f"linear-gradient(90deg, {color} 0%, {color} {pct}%, "
                f"{COLORS['surface']} {pct}%, {COLORS['surface']} 100%)"
            ),
        })
    return styles


# =====================================================
# 5. KPI SUMMARY (ringkasan angka besar di atas dashboard)
# =====================================================
total_customers = len(rfm_segments)
net_revenue = rfm_segments['Monetary'].sum()
champions_count = len(champions_display)
champions_share = round(
    champions_list['Monetary'].sum() / rfm_segments['Monetary'].sum() * 100, 1
)
avg_retention_m1 = round(
    cohort_retention.loc[cohort_retention['cohort_index'] == 1, 'retention_rate_pct'].mean(), 1
)


def kpi_card(eyebrow, value, sublabel, accent_color):
    """Card KPI dengan border aksen kiri tipis -- elemen signature dashboard ini."""
    return html.Div(
        style={
            'flex': '1', 'minWidth': '220px',
            'backgroundColor': COLORS['surface'],
            'borderLeft': f"4px solid {accent_color}",
            'borderRadius': '6px',
            'padding': '18px 20px',
            'boxShadow': '0 1px 2px rgba(22, 33, 62, 0.06)',
        },
        children=[
            html.Div(eyebrow, style={
                'fontFamily': FONT_MONO, 'fontSize': '11px', 'letterSpacing': '0.08em',
                'textTransform': 'uppercase', 'color': COLORS['text_muted'], 'marginBottom': '6px',
            }),
            html.Div(value, style={
                'fontFamily': FONT_DISPLAY, 'fontSize': '28px', 'fontWeight': '600',
                'color': COLORS['navy'], 'lineHeight': '1.1',
            }),
            html.Div(sublabel, style={
                'fontFamily': FONT_BODY, 'fontSize': '12.5px', 'color': COLORS['text_muted'],
                'marginTop': '4px',
            }),
        ]
    )


kpi_row = html.Div(
    style={'display': 'flex', 'gap': '14px', 'flexWrap': 'wrap', 'marginBottom': '28px'},
    children=[
        kpi_card('Net Revenue', f"£{net_revenue:,.0f}", 'Total nilai transaksi bersih', COLORS['navy']),
        kpi_card('Pelanggan Aktif', f"{total_customers:,}", 'Customer teranalisis (RFM)', COLORS['navy_soft']),
        kpi_card('Klien Champions', f"{champions_count:,}", 'Kandidat early access produk premium', COLORS['amber']),
        kpi_card('Kontribusi Champions', f"{champions_share}%", 'dari total revenue', COLORS['amber']),
        kpi_card('Retensi Bulan ke-1', f"{avg_retention_m1}%", 'Rata-rata seluruh cohort', COLORS['teal']),
    ]
)


# =====================================================
# 6. SUSUN DASHBOARD (DASH APP)
# =====================================================
app = Dash(__name__)

# Google Fonts di-inject lewat index_string -- dipasang sekali di <head>,
# bukan dimuat ulang setiap render komponen.
app.index_string = '''
<!DOCTYPE html>
<html>
    <head>
        {%metas%}
        <title>{%title%}</title>
        {%favicon%}
        {%css%}
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link href="https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=Inter:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
        <style>
            body { margin: 0; background-color: ''' + COLORS['bg'] + '''; }
            .kpi-card:hover { transform: translateY(-2px); transition: transform 0.15s ease; }
        </style>
    </head>
    <body>
        {%app_entry%}
        <footer>
            {%config%}
            {%scripts%}
            {%renderer%}
        </footer>
    </body>
</html>
'''

EYEBROW_STYLE = {
    'fontFamily': FONT_MONO, 'fontSize': '12px', 'letterSpacing': '0.1em',
    'textTransform': 'uppercase', 'color': COLORS['amber'], 'fontWeight': '500',
    'marginBottom': '4px',
}

app.layout = html.Div(
    style={
        'fontFamily': FONT_BODY, 'backgroundColor': COLORS['bg'],
        'maxWidth': '1280px', 'margin': '0 auto', 'padding': '32px 24px 60px',
    },
    children=[
        # --- Header ---
        html.Div('COHORT INTELLIGENCE · B2B SEGMENTATION', style=EYEBROW_STYLE),
        html.H1(
            'Optimasi Peluncuran Produk Premium B2B',
            style={'fontFamily': FONT_DISPLAY, 'color': COLORS['navy'], 'fontSize': '32px',
                   'margin': '0 0 6px 0', 'fontWeight': '700'}
        ),
        html.P(
            'Analisis retensi kohort dan segmentasi klien berbasis K-Means untuk menentukan '
            'target pasar paling layak bagi lini produk premium yang akan diluncurkan.',
            style={'color': COLORS['text_muted'], 'fontSize': '14.5px', 'maxWidth': '720px',
                   'marginBottom': '28px'}
        ),

        # --- KPI Cards ---
        kpi_row,

        # --- Baris 1: Heatmap (tengah, lebih besar) + Bar chart (kanan) ---
        html.Div(
            style={'display': 'flex', 'gap': '16px', 'flexWrap': 'wrap'},
            children=[
                html.Div(
                    dcc.Graph(figure=fig_heatmap, config={'displayModeBar': False}),
                    style={'flex': '2', 'minWidth': '500px', 'backgroundColor': COLORS['surface'],
                           'borderRadius': '8px', 'border': f"1px solid {COLORS['border']}", 'padding': '8px'}
                ),
                html.Div(
                    dcc.Graph(figure=fig_bar, config={'displayModeBar': False}),
                    style={'flex': '1', 'minWidth': '350px', 'backgroundColor': COLORS['surface'],
                           'borderRadius': '8px', 'border': f"1px solid {COLORS['border']}", 'padding': '8px'}
                ),
            ]
        ),

        html.Div(style={'height': '1px', 'backgroundColor': COLORS['border'], 'margin': '36px 0 24px'}),

        # --- Baris 2: Tabel actionable list klien Champions ---
        html.Div('ACTION LIST', style=EYEBROW_STYLE),
        html.H3(
            f'Klien "Loyal/Champions" untuk Tim Sales ({len(champions_display):,} klien)',
            style={'fontFamily': FONT_DISPLAY, 'color': COLORS['navy'], 'fontSize': '20px',
                   'margin': '0 0 6px 0'}
        ),
        html.P(
            'Kolom kontak (nama/email/telepon) perlu di-join dari sistem CRM menggunakan '
            'CustomerID sebagai key, karena dataset publik ini bersifat anonim.',
            style={'color': COLORS['text_muted'], 'fontSize': '13px', 'fontStyle': 'italic',
                   'marginBottom': '16px'}
        ),
        dash_table.DataTable(
            data=champions_display.to_dict('records'),
            columns=[
                {'name': 'Customer ID', 'id': 'CustomerID'},
                {'name': 'Tier Prioritas', 'id': 'PriorityTier'},
                {'name': 'Recency (hari)', 'id': 'Recency'},
                {'name': 'Frequency (invoice)', 'id': 'Frequency'},
                {'name': 'Net Revenue', 'id': 'Monetary',
                 'type': 'numeric',
                 'format': Format(symbol=Symbol.yes, symbol_prefix='£ ', group=Group.yes,
                                   precision=2, scheme=Scheme.fixed)},
                {'name': 'Return Rate', 'id': 'ReturnRate',
                 'type': 'numeric',
                 'format': Format(scheme=Scheme.percentage, precision=1)},
            ],
            page_size=15,
            sort_action='native',
            sort_by=[{'column_id': 'Monetary', 'direction': 'desc'}],
            filter_action='native',
            style_table={'overflowX': 'auto', 'border': f"1px solid {COLORS['border']}", 'borderRadius': '8px'},
            style_cell={
                'textAlign': 'center', 'padding': '10px', 'fontFamily': FONT_MONO,
                'fontSize': '13px', 'color': COLORS['text'], 'border': 'none',
                'borderBottom': f"1px solid {COLORS['border']}",
            },
            style_header={
                'backgroundColor': COLORS['navy'], 'color': 'white', 'fontWeight': '600',
                'fontFamily': FONT_BODY, 'fontSize': '12px', 'textTransform': 'uppercase',
                'letterSpacing': '0.04em', 'border': 'none',
            },
            # Catatan: style_active_cell tidak didukung di dash_table versi lama
            # (4.3.0), jadi warna highlight saat klik sel memakai default Dash.
            style_data_conditional=(
                [{'if': {'row_index': 'odd'}, 'backgroundColor': COLORS['bg']}]
                + data_bar_styles(champions_display, 'Monetary', COLORS['amber_soft'])
                + [
                    # Tier 1 ditandai teks tebal navy -- penanda prioritas utama
                    {'if': {'filter_query': '{PriorityTier} = "Tier 1 (Prioritas Utama)"', 'column_id': 'PriorityTier'},
                     'color': COLORS['navy'], 'fontWeight': '700'},
                    # Return rate tinggi: latar oranye lembut di SELURUH baris (bukan cuma teks),
                    # supaya benar-benar terlihat sebagai sinyal risiko, bukan terlewat.
                    {'if': {'filter_query': '{ReturnRate} > 0.15'},
                     'backgroundColor': '#FBEAD9', 'color': '#9A4A1C', 'fontWeight': '600'},
                ]
            ),
            tooltip_header={
                'Recency': 'Jumlah hari sejak transaksi terakhir klien (semakin kecil = semakin baru aktif)',
                'Frequency': 'Jumlah invoice unik yang pernah dibuat klien ini',
                'ReturnRate': 'Persentase nilai transaksi yang di-return dibanding total pembelian',
            },
            tooltip_delay=200,
            tooltip_duration=None,
        ),

        # --- Footer ---
        html.Div(
            'Sumber data: Online Retail II Dataset · Analisis Kohort & CLV B2B',
            style={'textAlign': 'center', 'color': COLORS['text_muted'], 'fontSize': '11.5px',
                   'fontFamily': FONT_MONO, 'marginTop': '48px'}
        ),
    ]
)

if __name__ == '__main__':
    app.run(debug=True)


