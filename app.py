import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ========== Config ==========
st.set_page_config(layout="wide", page_title="Acompanhamento de Meta Mensal - Vistorias")
st.title("📊 Acompanhamento de Meta Mensal - Vistorias")

st.markdown("""
<div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
  <h4 style="color: #cc3300; margin: 0;">👋 Bem-vindo(a) ao Painel de Acompanhamento de Metas!</h4>
  <p style="margin: 5px 0 0 0;">Acompanhe a performance por mês ou por dia usando o filtro à esquerda.</p>
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
if "empresa" in df.columns: df["empresa"] = df["empresa"].astype(str).str.upper()
if "unidade" in df.columns: df["unidade"] = df["unidade"].astype(str).str.upper()

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
    "TOKYO": {"BARRA DO CORDA": 677, "CHAPADINHA": 573, "SANTA INÊS": 2291, "SÃO JOÃO DOS PATOS": 453, "SÃO JOSÉ DE RIBAMAR": 2083},
    "STARCHECK": {"BACABAL": 1658, "BALSAS": 1722, "CAXIAS": 604, "CODÓ": 446, "PINHEIRO": 917, "SÃO LUÍS": 3272},
    "LOG": {"AÇAILÂNDIA": 1185, "CAROLINA": 126, "PRESIDENTE DUTRA": 926, "SÃO LUÍS": 4455, "TIMON": 896},
    "VELOX": {"ESTREITO": 482, "GRAJAÚ": 521, "IMPERATRIZ": 3488, "PEDREIRAS": 625, "SÃO LUÍS": 1926}
}
metas_gerais = {"TOKYO": 6076, "STARCHECK": 8620, "LOG": 7588, "VELOX": 7043}

# correção de possível digitação de cidade
if "VELOX" in metas_unidades and "SÃO LÍS" in metas_unidades["VELOX"]:
    metas_unidades["VELOX"]["SÃO LUÍS"] = metas_unidades["VELOX"].pop("SÃO LÍS")

# ========== Filtros (sidebar) ==========
st.sidebar.header("📅 Dias úteis do mês")
dias_uteis_total = int(st.sidebar.slider("Dias úteis no mês", 1, 31, 21, step=1, key="dias_total"))
dias_uteis_passados = int(st.sidebar.slider("Dias úteis já passados", 0, 31, 16, step=1, key="dias_passados"))
dias_uteis_restantes = max(dias_uteis_total - dias_uteis_passados, 1)

st.sidebar.markdown("---")
st.sidebar.subheader("🗓️ Filtro por Data do Relatório")

daily_mode = False
if df["__data__"].notna().any():
    datas_validas = sorted({d for d in df["__data__"] if pd.notna(d)})
    default_idx = 0
    if datas_validas: default_idx = 1 + len(datas_validas) - 1
    escolha = st.sidebar.selectbox(
        "Data do relatório",
        options=["(Mês inteiro)"] + [d.strftime("%d/%m/%Y") for d in datas_validas],
        index=default_idx
    )
    if escolha != "(Mês inteiro)":
        chosen_date = datetime.strptime(escolha, "%d/%m/%Y").date()
        df = df[df["__data__"] == chosen_date]
        daily_mode = True
else:
    st.sidebar.info("Sem coluna de data reconhecida. Exibindo mês inteiro.")

# ========== Filtro empresa ==========
empresas = sorted(df['empresa'].dropna().unique())
if len(empresas) == 0:
    st.warning("Não há dados para exibir. Verifique a planilha.")
    st.stop()

empresa_selecionada = st.selectbox("Selecione a Marca:", empresas)
df_filtrado = df[df['empresa'] == empresa_selecionada].copy()

# ========== Helpers ==========
def meta_marca_mes(marca: str) -> int:
    return int(metas_gerais.get(marca, 0))

def meta_unidade_mes(marca: str, unidade: str) -> int:
    return int(metas_unidades.get(marca, {}).get(unidade, 0))

def safe_div(a, b):
    return (a / b) if b else 0

# ========== Consolidados (marca) ==========
meta_mes_marca = meta_marca_mes(empresa_selecionada)
total_geral_marca = int(df_filtrado['total'].sum())
total_rev_marca = int(df_filtrado['revistorias'].sum())
total_liq_marca = total_geral_marca - total_rev_marca

if daily_mode:
    # ---- MODO DIÁRIO ----
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
    # ---- MODO MENSAL ----
    faltante_marca = max(meta_mes_marca - total_liq_marca, 0)
    media_diaria = safe_div(total_liq_marca, dias_uteis_passados)
    projecao_marca = media_diaria * dias_uteis_total
    tendencia = safe_div(projecao_marca, meta_mes_marca) * 100
    cards = [
        ("Meta da Marca", meta_mes_marca),
        ("Total Geral", total_geral_marca),
        ("Total Revistorias", total_rev_marca),
        ("Total Líquido", total_liq_marca),
        ("Faltante", faltante_marca),
        ("Necessidade/dia", int(safe_div(faltante_marca, dias_uteis_restantes))),
        ("Projeção", int(projecao_marca)),
        ("Tendência", f"{tendencia:.0f}% {'🚀' if tendencia >= 100 else '😟'}"),
    ]

# ========== Estilo cartões ==========
st.markdown("""
<style>
.card-container { display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap; }
.card { background-color: #f5f5f5; padding: 20px; border-radius: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.1); text-align: center;
        min-width: 170px; flex: 1; }
.card h4 { color: #cc3300; margin: 0 0 8px; font-size: 16px; }
.card h2 { margin: 0; font-size: 26px; font-weight: bold; color: #222; }
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
        total_label = "Total (Dia)"
        rev_label = "Revistorias (Dia)"
        liq_label = "Total Líquido (Dia)"
        tend_label = "Tendência (Dia)"
    else:
        faltante = max(meta_mes - liq, 0)
        media = safe_div(liq, dias_uteis_passados)
        proj_final = media * dias_uteis_total
        tendencia_u = safe_div(proj_final, meta_mes) * 100 if meta_mes else 0
        tendencia_txt = f"{tendencia_u:.0f}% {'🚀' if tendencia_u >= 100 else '😟'}"
        meta_col = meta_mes
        falt_label = "Faltante (sobre Líquido)"
        nec_dia = safe_div(faltante, dias_uteis_restantes)
        total_label = "Total"
        rev_label = "Revistorias"
        liq_label = "Total Líquido"
        tend_label = "Tendência"

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

# ========== Gráfico ==========
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

agg_geral = df.groupby("empresa", dropna=False).agg(total=("total","sum"), rev=("revistorias","sum")).reset_index()
real_total = int(agg_geral["total"].sum())
rev_total = int(agg_geral["rev"].sum())
liq_total = real_total - rev_total

meta_mes_geral = sum(metas_gerais.values())
if daily_mode:
    meta_dia_geral = safe_div(meta_mes_geral, dias_uteis_total)
    falt_geral = max(int(round(meta_dia_geral)) - liq_total, 0)
    tendencia_g = safe_div(liq_total, meta_dia_geral) * 100
    geral_cards = [
        ("Meta do Dia (Geral)", int(round(meta_dia_geral))),
        ("Total Geral (Dia)", real_total),
        ("Total Revistorias (Dia)", rev_total),
        ("Total Líquido (Dia)", liq_total),
        ("Faltante (Dia)", falt_geral),
        ("Necessidade/dia (Dia)", falt_geral),
        ("Projeção (Dia)", liq_total),
        ("Tendência (Dia)", f"{tendencia_g:.0f}% {'🚀' if tendencia_g >= 100 else '😟'}"),
    ]
else:
    falt_geral = max(meta_mes_geral - liq_total, 0)
    media_g = safe_div(liq_total, dias_uteis_passados)
    proj_g = media_g * dias_uteis_total
    tendencia_g = safe_div(proj_g, meta_mes_geral) * 100
    geral_cards = [
        ("Meta Geral", meta_mes_geral),
        ("Total Geral", real_total),
        ("Total Revistorias", rev_total),
        ("Total Líquido", liq_total),
        ("Faltante", falt_geral),
        ("Necessidade/dia", int(safe_div(falt_geral, dias_uteis_restantes))),
        ("Projeção", int(proj_g)),
        ("Tendência", f"{tendencia_g:.0f}% {'🚀' if tendencia_g >= 100 else '😟'}"),
    ]

st.markdown(
    "<div class='card-container'>" +
    "".join([f"<div class='card'><h4>{t}</h4><h2>{v}</h2></div>" for t, v in geral_cards]) +
    "</div>", unsafe_allow_html=True
)
