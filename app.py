import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import altair as alt
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, date, timedelta
import calendar

# ========== Config ==========
st.set_page_config(layout="wide", page_title="Acompanhamento de Meta Mensal - Vistorias")
st.title("📊 Acompanhamento de Meta Mensal - Vistorias")

st.markdown("""
<div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
  <h4 style="color: #cc3300; margin: 0;">👋 Bem-vindo(a) ao Painel de Acompanhamento de Metas!</h4>
  <p style="margin: 5px 0 0 0;">Acompanhe a performance por mês ou por dia usando o filtro à esquerda. Veja também o <b>calendário (heatmap)</b>, a <b>tabela com meta ajustada</b> e o <b>ranking diário</b>.</p>
</div>
""", unsafe_allow_html=True)

# ========== Conexão Google Sheets ==========
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

SHEET_KEY = "1ooMhPk-R-Etzut4BHkxCTgYZx8fztHzDlhyXuS9TLGo"
sheet = client.open_by_key(SHEET_KEY).sheet1
data = sheet.get_all_records()
df = pd.DataFrame(data)

# ========== Limpeza / Tipos ==========
if "empresa" in df.columns:
    df["empresa"] = (df["empresa"].astype(str).str.upper()
                     .str.strip().str.replace(r"\s+", " ", regex=True))
if "unidade" in df.columns:
    df["unidade"] = (df["unidade"].astype(str).str.upper()
                     .str.strip().str.replace(r"\s+", " ", regex=True))

for col in ["total", "revistorias", "ticket_medio", "%_190"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

df["ticket_medio_real"] = df["ticket_medio"] / 100 if "ticket_medio" in df.columns else 0
if "%_190" not in df.columns: df["%_190"] = 0
if "revistorias" not in df.columns: df["revistorias"] = 0

# ---- Data (aceita DATA ou data_relatorio) ----
date_candidates = [c for c in ["data_relatorio", "DATA", "Data", "data"] if c in df.columns]
date_col = date_candidates[0] if date_candidates else None

def parse_date_value(x):
    if pd.isna(x) or x == "": return pd.NaT
    if isinstance(x, (int, float)) and not isinstance(x, bool):
        try: return (pd.to_datetime("1899-12-30") + pd.to_timedelta(int(x), unit="D")).date()
        except: pass
    s = str(x).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try: return datetime.strptime(s, fmt).date()
        except: continue
    try: return pd.to_datetime(s).date()
    except: return pd.NaT

if date_col:
    df["__data__"] = df[date_col].apply(parse_date_value)
else:
    df["__data__"] = pd.NaT

# ========== Metas ==========
metas_unidades = {
    "TOKYO": {"BARRA DO CORDA": 650, "CHAPADINHA": 550, "SANTA INÊS": 2200, "SÃO JOÃO DOS PATOS": 435, "SÃO JOSÉ DE RIBAMAR": 2000},
    "STARCHECK": {"BACABAL": 1640, "BALSAS": 1505, "CAXIAS": 560, "CODÓ": 380, "PINHEIRO": 900, "SÃO LUÍS": 3200},
    "LOG": {"AÇAILÂNDIA": 1100, "CAROLINA": 135, "PRESIDENTE DUTRA": 875, "SÃO LUÍS": 4240, "TIMON": 980},
    "VELOX": {"ESTREITO": 463, "GRAJAÚ": 500, "IMPERATRIZ": 3350, "PEDREIRAS": 600, "SÃO LUÍS": 1850}
}
metas_gerais = {"TOKYO": 5835, "STARCHECK": 8305, "LOG": 7330, "VELOX": 6763}
# corrigir possível variação de nome
if "VELOX" in metas_unidades and "SÃO LÍS" in metas_unidades["VELOX"]:
    metas_unidades["VELOX"]["SÃO LUÍS"] = metas_unidades["VELOX"].pop("SÃO LÍS")

# =========================
# Guardar histórico completo e visão filtrável
# =========================
df_full = df.copy()

# ========== Sidebar ==========
st.sidebar.header("📅 Dias úteis do mês")
dias_uteis_total = int(st.sidebar.slider("Dias úteis no mês", 1, 31, 21, step=1, key="dias_total"))
dias_uteis_passados = int(st.sidebar.slider("Dias úteis já passados", 0, 31, 16, step=1, key="dias_passados"))
dias_uteis_restantes = max(dias_uteis_total - dias_uteis_passados, 1)

st.sidebar.markdown("---")
st.sidebar.subheader("🗓️ Filtro por Data do Relatório")
daily_mode = False
chosen_date = None

if df_full["__data__"].notna().any():
    datas_validas = sorted({d for d in df_full["__data__"] if pd.notna(d)})
    default_idx = 0
    if datas_validas: default_idx = 1 + len(datas_validas) - 1
    escolha = st.sidebar.selectbox(
        "Data do relatório",
        options=["(Mês inteiro)"] + [d.strftime("%d/%m/%Y") for d in datas_validas],
        index=default_idx
    )
    if escolha != "(Mês inteiro)":
        chosen_date = datetime.strptime(escolha, "%d/%m/%Y").date()
        df_view = df_full[df_full["__data__"] == chosen_date]
        daily_mode = True
    else:
        df_view = df_full.copy()
else:
    st.sidebar.info("Sem coluna de data reconhecida. Exibindo mês inteiro.")
    df_view = df_full.copy()

# ========== Filtro empresa ==========
empresas = sorted(df_view['empresa'].dropna().unique())
if len(empresas) == 0:
    st.warning("Não há dados para exibir. Verifique a planilha.")
    st.stop()

empresa_selecionada = st.selectbox("Selecione a Marca:", empresas)

# df_filtrado: visão atual (mês ou dia) para cartões/tabelas/gráfico
df_filtrado = df_view[df_view['empresa'] == empresa_selecionada].copy()
# df_marca_all: histórico completo da marca (para heatmap/catch-up/ranking)
df_marca_all = df_full[df_full["empresa"] == empresa_selecionada].copy()

# ========== Helpers ==========
def meta_marca_mes(marca: str) -> int:
    return int(metas_gerais.get(marca, 0))

def meta_unidade_mes(marca: str, unidade: str) -> int:
    return int(metas_unidades.get(marca, {}).get(unidade, 0))

def safe_div(a, b): return (a / b) if b else 0
def is_workday(d: date) -> bool: return d.weekday() < 5  # seg–sex

# ========== Consolidado (marca) ==========
meta_mes_marca = meta_marca_mes(empresa_selecionada)
total_geral_marca = int(df_filtrado['total'].sum())
total_rev_marca = int(df_filtrado['revistorias'].sum())
total_liq_marca = total_geral_marca - total_rev_marca

if daily_mode:
    meta_dia_marca = safe_div(meta_mes_marca, dias_uteis_total)
    faltante_dia = max(int(round(meta_dia_marca)) - total_liq_marca, 0)
    tendencia = safe_div(total_liq_marca, meta_dia_marca) * 100
    cards = [
        ("Meta do Dia", int(round(meta_dia_marca))),
        ("Total Geral (Dia)", total_geral_marca),
        ("Total Revistorias (Dia)", total_rev_marca),
        ("Total Líquido (Dia)", total_liq_marca),
        ("Faltante (Dia)", faltante_dia),
        ("Necessidade/dia (Dia)", faltante_dia),
        ("Projeção (Dia)", total_liq_marca),
        ("Tendência (Dia)", f"{tendencia:.0f}% {'🚀' if tendencia >= 100 else '😟'}"),
    ]
else:
    faltante_marca = max(meta_mes_marca - total_liq_marca, 0)
    media_diaria = safe_div(total_liq_marca, dias_uteis_passados)
    projecao_marca_total = total_liq_marca + media_diaria * dias_uteis_restantes
    tendencia = safe_div(projecao_marca_total, meta_mes_marca) * 100
    cards = [
        ("Meta da Marca", meta_mes_marca),
        ("Total Geral", total_geral_marca),
        ("Total Revistorias", total_rev_marca),
        ("Total Líquido", total_liq_marca),
        ("Faltante", faltante_marca),
        ("Necessidade/dia", int(safe_div(faltante_marca, dias_uteis_restantes))),
        ("Projeção (Fim do mês)", int(projecao_marca_total)),
        ("Tendência", f"{tendencia:.0f}% {'🚀' if tendencia >= 100 else '😟'}"),
    ]

st.markdown("""
<style>
.card-container { display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap; }
.card { background-color: #f5f5f5; padding: 20px; border-radius: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.1); text-align: center;
        min-width: 170px; flex: 1; }
.card h4 { color: #cc3300; margin: 0 0 8px; font-size: 16px; }
.card h2 { margin: 0; font-size: 26px; font-weight: bold; color: #222; }
.section-title { font-size: 20px; font-weight: 700; margin: 18px 0 8px; }
</style>
""", unsafe_allow_html=True)

st.markdown(f"### 🏢 Consolidado - {empresa_selecionada}")
st.markdown(
    "<div class='card-container'>" +
    "".join([f"<div class='card'><h4>{t}</h4><h2>{v}</h2></div>" for t, v in cards]) +
    "</div>", unsafe_allow_html=True
)

# ========== Tabela por unidade ==========
st.subheader("📍 Indicadores por Unidade")

agr = df_filtrado.groupby("unidade", dropna=False, as_index=False).agg(
    total=("total", "sum"),
    rev=("revistorias", "sum"),
    ticket_medio_real=("ticket_medio_real", "mean"),
    pct190=("%_190", "mean")
)

linhas = []
for _, r in agr.iterrows():
    unidade = r["unidade"]
    total = int(r["total"])
    rev = int(r["rev"])
    liq = total - rev

    meta_mes = meta_unidade_mes(empresa_selecionada, unidade)
    if daily_mode:
        meta_dia = safe_div(meta_mes, dias_uteis_total)
        faltante = max(int(round(meta_dia)) - liq, 0)
        tendencia_u = safe_div(liq, meta_dia) * 100 if meta_dia else 0
        tendencia_txt = f"{tendencia_u:.0f}% {'🚀' if tendencia_u >= 100 else '😟'}"
        meta_col = int(round(meta_dia))
        falt_label = "Faltante (Dia)"
        nec_dia = faltante
        total_label = "Total (Dia)"; rev_label = "Revistorias (Dia)"; liq_label = "Total Líquido (Dia)"; tend_label = "Tendência (Dia)"
    else:
        faltante = max(meta_mes - liq, 0)
        media = safe_div(liq, dias_uteis_passados)
        proj_final = liq + media * dias_uteis_restantes
        tendencia_u = safe_div(proj_final, meta_mes) * 100 if meta_mes else 0
        tendencia_txt = f"{tendencia_u:.0f}% {'🚀' if tendencia_u >= 100 else '😟'}"
        meta_col = meta_mes
        falt_label = "Faltante (sobre Líquido)"
        nec_dia = safe_div(faltante, dias_uteis_restantes)
        total_label = "Total"; rev_label = "Revistorias"; liq_label = "Total Líquido"; tend_label = "Tendência"

    ticket = round(float(r["ticket_medio_real"]), 2)
    icon_ticket = "✅" if ticket >= 161.50 else "❌"
    pct190 = float(r["pct190"])
    icon_190 = "✅" if pct190 >= 25 else "⚠️" if pct190 >= 20 else "❌"

    linhas.append({
        "Unidade": unidade,
        "Meta do Dia" if daily_mode else "Meta": int(meta_col),
        total_label: total,
        rev_label: rev,
        liq_label: liq,
        falt_label: int(faltante),
        "Necessidade/dia": int(nec_dia) if daily_mode else round(nec_dia, 1),
        tend_label: tendencia_txt,
        "Ticket Médio (R$)": f"R$ {ticket:.2f} {icon_ticket}",
        "% ≥ R$190": f"{pct190:.0f}% {icon_190}"
    })

st.dataframe(pd.DataFrame(linhas), use_container_width=True)

# ========== Gráfico (matplotlib) ==========
st.subheader("📊 Produção Realizada por Unidade " + ("(Líquido - Dia)" if daily_mode else "(Líquido)"))
unidades = [d["Unidade"] for d in linhas]
prod_liq = [d["Total Líquido (Dia)"] if daily_mode else d["Total Líquido"] for d in linhas]

fig, ax = plt.subplots(figsize=(10, 5))
barras = ax.bar(unidades, prod_liq)
for b in barras:
    h = b.get_height()
    ax.annotate(f'{int(h)}', xy=(b.get_x()+b.get_width()/2, h), xytext=(0,5),
                textcoords="offset points", ha='center', va='bottom', fontsize=10, fontweight='bold')
plt.xticks(rotation=0)
ax.set_ylabel("Produção (Líquido)")
ax.set_xlabel("Unidade")
ax.set_title("Produção por Unidade" + (" - Dia" if daily_mode else ""))
st.pyplot(fig)

# ========== Consolidado Geral ==========
st.markdown("---")
st.markdown("## 🏢 Consolidado Geral - Total das 4 Marcas")

agg_geral = df_view.groupby("empresa", dropna=False).agg(total=("total","sum"), rev=("revistorias","sum")).reset_index()
real_total = int(agg_geral["total"].sum())
rev_total = int(agg_geral["rev"].sum())
liq_total = real_total - rev_total

meta_mes_geral = sum(metas_gerais.values())
if daily_mode:
    meta_dia_geral = safe_div(meta_mes_geral, dias_uteis_total)
    falt_geral = max(int(round(meta_dia_geral)) - liq_total, 0)
    tendencia_g = safe_div(liq_total, meta_dia_geral) * 100
    geral_cards = [
        ("Meta do Dia (Geral)", int(round(meta_dia_geral))), ("Total Geral (Dia)", real_total),
        ("Total Revistorias (Dia)", rev_total), ("Total Líquido (Dia)", liq_total),
        ("Faltante (Dia)", falt_geral), ("Necessidade/dia (Dia)", falt_geral),
        ("Projeção (Dia)", liq_total), ("Tendência (Dia)", f"{tendencia_g:.0f}% {'🚀' if tendencia_g >= 100 else '😟'}"),
    ]
else:
    falt_geral = max(meta_mes_geral - liq_total, 0)
    media_g = safe_div(liq_total, dias_uteis_passados)
    proj_g_total = liq_total + media_g * dias_uteis_restantes
    tendencia_g = safe_div(proj_g_total, meta_mes_geral) * 100
    geral_cards = [
        ("Meta Geral", meta_mes_geral), ("Total Geral", real_total), ("Total Revistorias", rev_total),
        ("Total Líquido", liq_total), ("Faltante", falt_geral),
        ("Necessidade/dia", int(safe_div(falt_geral, dias_uteis_restantes))),
        ("Projeção (Fim do mês)", int(proj_g_total)), ("Tendência", f"{tendencia_g:.0f}% {'🚀' if tendencia_g >= 100 else '😟'}"),
    ]

st.markdown(
    "<div class='card-container'>" +
    "".join([f"<div class='card'><h4>{t}</h4><h2>{v}</h2></div>" for t, v in geral_cards]) +
    "</div>", unsafe_allow_html=True
)

# =========================
# 📅 Heatmap do Mês (Calendário) — Altair (tamanho + tooltip)
# =========================
st.markdown("---")
st.markdown("<div class='section-title'>📅 Heatmap do Mês (Calendário)</div>", unsafe_allow_html=True)

HEAT_W, HEAT_H = 980, 420  # tamanho que você gostou

datas_marca = sorted([d for d in df_marca_all["__data__"].unique() if pd.notna(d)])
if datas_marca:
    last_date = datas_marca[-1]
    months_available = sorted({(d.year, d.month) for d in datas_marca})
    month_labels = [f"{y}-{m:02d}" for (y, m) in months_available]
    default_month = f"{last_date.year}-{last_date.month:02d}"
    default_idx = month_labels.index(default_month) if default_month in month_labels else len(month_labels)-1
    month_choice = st.selectbox("Mês de referência (marca)", options=month_labels, index=default_idx, key="mes_heatmap")
    ref_year, ref_month = map(int, month_choice.split("-"))
else:
    today = date.today()
    ref_year, ref_month = today.year, today.month

mask_month = df_marca_all["__data__"].apply(lambda d: isinstance(d, date) and d.year == ref_year and d.month == ref_month)
df_month = df_marca_all[mask_month].copy()

if len(df_month) > 0:
    tmp = (df_month.groupby("__data__", as_index=False)
                  .agg(total=("total", "sum"),
                       rev=("revistorias", "sum")))
    tmp["liq"] = (tmp["total"] - tmp["rev"]).astype(int)
    daily_liq = tmp[["__data__", "liq"]]
    last_data_day = daily_liq["__data__"].max()
else:
    daily_liq = pd.DataFrame(columns=["__data__", "liq"])
    last_data_day = None

meta_dia_base = (metas_gerais.get(empresa_selecionada, 0) / dias_uteis_total) if dias_uteis_total else 0
metric_choice = st.radio("Cor do heatmap baseada em:", ["% da meta do dia", "Total Líquido"], horizontal=True, key="heatmap_metric")
show_values = st.checkbox("Mostrar valor dentro das células", value=False, key="heatmap_labels")

first_weekday, n_days = calendar.monthrange(ref_year, ref_month)
liq_map = daily_liq.set_index("__data__")["liq"].to_dict()

records = []
ord_dow = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]

for day in range(1, n_days + 1):
    d = date(ref_year, ref_month, day)
    if (last_data_day is None) or (d > last_data_day) or (d not in liq_map):
        liq = np.nan
    else:
        liq = float(liq_map[d])
    pct = (liq / meta_dia_base * 100) if (not np.isnan(liq) and meta_dia_base) else np.nan

    dow_idx = d.weekday()
    dow_label = ord_dow[dow_idx]
    week_index = (day + first_weekday - 1) // 7

    if metric_choice == "% da meta do dia":
        value = pct if (not np.isnan(pct) and dow_idx < 5) else np.nan  # Sáb/Dom em branco
        val_label_str = f"{pct:.0f}%" if (show_values and not np.isnan(pct) and dow_idx < 5) else ""
    else:
        value = liq if not np.isnan(liq) else np.nan
        val_label_str = f"{int(liq)}" if (show_values and not np.isnan(liq)) else ""

    records.append({
        "date": pd.to_datetime(d),
        "day": day,
        "dow_label": dow_label,
        "week_index": week_index,
        "liq": liq,
        "pct": pct,
        "value": value,
        "val_label_str": val_label_str
    })

cal_df = pd.DataFrame.from_records(records)

base = alt.Chart(cal_df).properties(width=HEAT_W, height=HEAT_H)

color_scale = alt.Scale(scheme='viridis')
color_title = 'Líquido'
if metric_choice == "% da meta do dia":
    color_scale = alt.Scale(scheme='viridis', domain=[0, 120])  # 0–120%
    color_title = '%'

heat = base.mark_rect().encode(
    x=alt.X('dow_label:N', title='', scale=alt.Scale(domain=ord_dow)),
    y=alt.Y('week_index:O', title='', sort=alt.SortField('week_index', order='ascending'), axis=None),
    color=alt.Color('value:Q', title=color_title, scale=color_scale),
    tooltip=[
        alt.Tooltip('date:T', title='Data'),
        alt.Tooltip('liq:Q',  title='Líquido', format='.0f'),
        alt.Tooltip('pct:Q',  title='% Meta',  format='.0f')
    ]
)

labels_day = base.mark_text(baseline='middle', dy=-8, fontSize=12, color='black').encode(
    x='dow_label:N', y='week_index:O', text='day:Q'
)

chart = heat + labels_day
if show_values:
    labels_val = base.mark_text(baseline='middle', dy=10, fontSize=11, color='black').encode(
        x='dow_label:N', y='week_index:O', text='val_label_str:N'
    )
    chart = chart + labels_val

st.altair_chart(chart, use_container_width=False)

# ============ Tabela de Meta Ajustada (Catch-up) ============
st.markdown("<div class='section-title'>📋 Acompanhamento Diário com Meta Ajustada (Catch-up)</div>", unsafe_allow_html=True)

unidades_marca = ["(Consolidado da Marca)"] + sorted(df_marca_all["unidade"].dropna().unique().tolist())
un_sel = st.selectbox("Unidade", options=unidades_marca, index=0, key="un_meta_tab")

mask_month_brand = df_marca_all["__data__"].apply(lambda d: isinstance(d, date) and d.year==ref_year and d.month==ref_month)
df_month_brand = df_marca_all[mask_month_brand].copy()
if un_sel != "(Consolidado da Marca)":
    df_month_brand = df_month_brand[df_month_brand["unidade"] == un_sel]

daily_series = (df_month_brand.groupby("__data__")
                .apply(lambda x: int(x["total"].sum() - x["revistorias"].sum()))
                .sort_index())

meta_mes_ref = meta_marca_mes(empresa_selecionada) if un_sel == "(Consolidado da Marca)" else meta_unidade_mes(empresa_selecionada, un_sel)
meta_dia_const = safe_div(meta_mes_ref, dias_uteis_total)

month_start = date(ref_year, ref_month, 1)
month_end = date(ref_year, ref_month, calendar.monthrange(ref_year, ref_month)[1])
all_days = pd.date_range(month_start, month_end, freq="D")
workdays_dates = [ts.date() for ts in all_days if is_workday(ts.date())]

remaining_map = {}
for idx, wd in enumerate(workdays_dates):
    remaining_map[wd] = len(workdays_dates) - idx

rows = []
acum_real = 0
for d, liq in daily_series.items():
    if d in remaining_map:
        dias_restantes_incl_hoje = remaining_map[d]
        meta_dia_ajustada = safe_div((meta_mes_ref - acum_real), dias_restantes_incl_hoje)
    else:
        meta_dia_ajustada = 0  # sábado/domingo sem meta

    diff_dia = liq - meta_dia_ajustada
    acum_real += liq
    saldo_restante = meta_mes_ref - acum_real

    rows.append({
        "Data": d.strftime("%d/%m/%Y"),
        "Meta (constante)": round(meta_dia_const, 1),
        "Meta Ajustada (catch-up)": round(meta_dia_ajustada, 1),
        "Realizado Líquido": int(liq),
        "Δ do Dia (Real − Meta Aj.)": round(diff_dia, 1),
        "Acumulado Líquido": int(acum_real),
        "Saldo p/ Bater Meta": int(saldo_restante),
        "Status": "✅" if liq >= meta_dia_ajustada and meta_dia_ajustada > 0 else ("—" if meta_dia_ajustada == 0 else "❌")
    })

st.dataframe(pd.DataFrame(rows), use_container_width=True)

# ============ Ranking Diário Top/Bottom 5 ============
st.markdown("<div class='section-title'>🏆 Ranking Diário por Unidade (Tendência do Dia e Variação vs Ontem)</div>", unsafe_allow_html=True)

if chosen_date and (isinstance(chosen_date, date) and chosen_date.year==ref_year and chosen_date.month==ref_month):
    rank_date = chosen_date
else:
    rank_date = max(daily_series.index) if len(daily_series) else None

if rank_date is None:
    st.info("Ainda não há dados neste mês para montar o ranking.")
else:
    df_unit_daily = (df_marca_all
        .groupby(["unidade", "__data__"])
        .apply(lambda x: int(x["total"].sum() - x["revistorias"].sum()))
        .rename("liq")
        .reset_index())

    today_df = df_unit_daily[df_unit_daily["__data__"] == rank_date].copy()

    def last_workday_with_data(u):
        prevs = df_unit_daily[(df_unit_daily["unidade"] == u) & (df_unit_daily["__data__"] < rank_date)]
        prevs = prevs[prevs["__data__"].apply(is_workday)]
        if len(prevs) == 0:
            return None, 0
        row = prevs.sort_values("__data__").iloc[-1]
        return row["__data__"], row["liq"]

    prev_map = []
    for u in today_df["unidade"].unique():
        dprev, liqprev = last_workday_with_data(u)
        prev_map.append({"unidade": u, "__data_prev__": dprev, "liq_prev": liqprev})
    prev_df = pd.DataFrame(prev_map)

    metas_u = pd.DataFrame(
        [(u, meta_unidade_mes(empresa_selecionada, u)) for u in today_df["unidade"].unique()],
        columns=["unidade", "meta_mes"]
    )

    df_rank = (today_df.merge(prev_df, on="unidade", how="left")
                        .merge(metas_u, on="unidade", how="left"))
    df_rank["meta_dia"] = df_rank["meta_mes"] / dias_uteis_total

    workday_rank = is_workday(rank_date)

    df_rank["pct_hoje"] = np.where(df_rank["meta_dia"] > 0,
                                   (df_rank["liq"] / df_rank["meta_dia"]) * 100, 0.0)
    df_rank["pct_ontem"] = np.where(
        (df_rank["meta_dia"] > 0) & df_rank["__data_prev__"].notna(),
        (df_rank["liq_prev"] / df_rank["meta_dia"]) * 100,
        np.nan
    )
    df_rank["delta_pct"] = df_rank["pct_hoje"] - df_rank["pct_ontem"]

    order_col = "pct_hoje" if workday_rank else "liq"
    df_rank = df_rank.sort_values(order_col, ascending=False)

    col1, col2 = st.columns(2)

    def fmt_delta(x):
        if pd.isna(x): return "—"
        arrow = "⬆️" if x > 0 else ("⬇️" if x < 0 else "➡️")
        return f"{arrow} {abs(x):.0f} pp"

    def render_rank(df_sub, title, container):
        with container:
            st.markdown(f"**{title} — {rank_date.strftime('%d/%m/%Y')}**")
            linhas = []
            for _, r in df_sub.iterrows():
                linhas.append({
                    "Unidade": r["unidade"],
                    "% do Dia": f"{r['pct_hoje']:.0f}%" if workday_rank else "—",
                    "Δ vs Ontem": fmt_delta(r["delta_pct"]) if workday_rank else "—",
                    "Líquido (Dia)": int(r["liq"]),
                    "Meta do Dia": int(round(r["meta_dia"])) if (workday_rank and r["meta_dia"] > 0) else 0
                })
            st.dataframe(pd.DataFrame(linhas), use_container_width=True)

    render_rank(df_rank.head(5), "TOP 5", col1)
    render_rank(df_rank.tail(5).sort_values(order_col, ascending=True), "BOTTOM 5", col2)
