# app.py — robusto (retry + cache) + separação por marca (5 links)
import re, calendar, time, random
from datetime import datetime, date

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import altair as alt

import gspread
from gspread.exceptions import APIError
from oauth2client.service_account import ServiceAccountCredentials
# (se quiser migrar depois: from google.oauth2.service_account import Credentials)

# ================= CONFIG BÁSICA =================
st.set_page_config(layout="wide", page_title="Acompanhamento de Meta Mensal - Vistorias")

# ======= ESCOPO DE MARCA (ALL | LOG | STARCHECK | TOKYO | VELOX) =======
VALID_BRANDS = {"ALL", "LOG", "STARCHECK", "TOKYO", "VELOX"}

def get_brand_scope():
    b = str(st.secrets.get("DEFAULT_BRAND", "ALL")).strip().upper()
    return b if b in VALID_BRANDS else "ALL"

BRAND_SCOPE = get_brand_scope()
title_suffix = "" if BRAND_SCOPE == "ALL" else f" — {BRAND_SCOPE}"

st.title(f"📊 Acompanhamento de Meta Mensal - Vistorias{title_suffix}")

st.markdown("""
<div style="background-color:#f0f2f6;padding:15px;border-radius:10px;margin-bottom:20px;box-shadow:0 1px 3px rgba(0,0,0,.1);">
  <h4 style="color:#cc3300;margin:0;">👋 Bem-vindo(a) ao Painel de Acompanhamento de Metas!</h4>
  <p style="margin:5px 0 0 0;">Acompanhe a performance por mês ou por dia usando o filtro à esquerda. Veja também o <b>calendário (heatmap)</b>, a <b>tabela com meta ajustada</b> e o <b>ranking diário</b>.</p>
</div>
""", unsafe_allow_html=True)

# ================= CONEXÃO GOOGLE SHEETS (com retry + cache) =================
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def _should_retry(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(s in msg for s in [
        "rate limit", "quota", "429", "internal error", "backend error",
        "failed to fetch", "fetch_sheet_metadata", "service unavailable", "deadline"
    ])

def _with_retry(fn, *, tries=5, base=0.8, jitter=0.3):
    last = None
    for i in range(tries):
        try:
            return fn()
        except APIError as e:
            last = e
            if i == tries - 1 or not _should_retry(e):
                raise
            time.sleep(base * (2 ** i) + random.random() * jitter)
        except Exception as e:
            last = e
            if i == tries - 1 or not _should_retry(e):
                raise
            time.sleep(base * (2 ** i) + random.random() * jitter)
    if last:
        raise last

@st.cache_resource(show_spinner=False)
def _get_client():
    creds_dict = st.secrets["gcp_service_account"]
    # oauth2client (como já usa hoje):
    creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
    # Se migrar futuramente:
    # creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPE)
    return gspread.authorize(creds)

@st.cache_data(show_spinner=False, ttl=600)
def read_sheet_records_by_key(sheet_key: str, tab: str | None):
    """Lê todos os registros de uma worksheet como lista de dicts (cache 10 min)."""
    client = _get_client()
    sh = _with_retry(lambda: client.open_by_key(sheet_key))
    ws = _with_retry(lambda: (sh.worksheet(tab) if tab else sh.sheet1))
    rows = _with_retry(lambda: ws.get_all_records())
    return rows

# ====== PLANILHA-ÍNDICE ======
INDEX_SHEET_ID = "1L55P-vJifVEg6BHBGVLd00m3AXsz7hEyCPMA60G6Jms"
INDEX_TAB_ARQS  = "ARQUIVOS"   # colunas: URL | MÊS | ATIVO
INDEX_TAB_METAS = "METAS"      # colunas: MÊS | EMPRESA | UNIDADE | DIAS_UTEIS | META_MENSAL

# =================== HELPERS ===================
ID_RE = re.compile(r"/d/([a-zA-Z0-9-_]+)")
def _sheet_id(s: str):
    s = (s or "").strip()
    m = ID_RE.search(s)
    if m: return m.group(1)
    return s if re.fullmatch(r"[A-Za-z0-9-_]{20,}", s) else None

def _ym_token(x):
    s = str(x).strip()
    if re.fullmatch(r"\d{2}/\d{4}", s):
        mm, yy = s.split("/")
        return f"{yy}-{int(mm):02d}"
    if re.fullmatch(r"\d{4}-\d{2}", s):
        return s
    return None

def parse_date_value(x):
    # versão segura: aceita floats do Excel sem truncar o dia
    if pd.isna(x) or x == "": return pd.NaT
    if isinstance(x, (int,float)) and not isinstance(x,bool):
        try:
            base = pd.to_datetime("1899-12-30")
            return (base + pd.to_timedelta(float(x), unit="D")).date()
        except: 
            pass
    s = str(x).strip()
    for fmt in ("%d/%m/%Y","%Y-%m-%d","%d-%m-%Y"):
        try: return datetime.strptime(s, fmt).date()
        except: pass
    try: return pd.to_datetime(s).date()
    except: return pd.NaT

def safe_div(a,b): return (a/b) if b else 0
def is_workday(d: date) -> bool: return isinstance(d, date) and d.weekday() < 5

# =================== METAS BASE (21 dias) ===================
metas_unidades_base = {
    "TOKYO": {"BARRA DO CORDA": 677, "CHAPADINHA": 573, "SANTA INÊS": 2291, "SÃO JOÃO DOS PATOS": 453, "SÃO JOSÉ DE RIBAMAR": 2083},
    "STARCHECK": {"BACABAL": 1658, "BALSAS": 1642, "CAXIAS": 604, "CODÓ": 446, "PINHEIRO": 917, "SÃO LUÍS": 3272},
    "LOG": {"AÇAILÂNDIA": 1185, "CAROLINA": 126, "PRESIDENTE DUTRA": 926, "SÃO LUÍS": 4455, "TIMON": 896},
    "VELOX": {"ESTREITO": 482, "GRAJAÚ": 496, "IMPERATRIZ": 3488, "PEDREIRAS": 625, "SÃO LUÍS": 1926}
}
if "VELOX" in metas_unidades_base and "SÃO LÍS" in metas_unidades_base["VELOX"]:
    metas_unidades_base["VELOX"]["SÃO LUÍS"] = metas_unidades_base["VELOX"].pop("SÃO LÍS")
BASE_21 = 21

# =================== LER ÍNDICE: ARQUIVOS + METAS (com cache e fail-soft) ===================
try:
    rows_arqs = read_sheet_records_by_key(INDEX_SHEET_ID, INDEX_TAB_ARQS)
except Exception as e:
    st.error(f"Não foi possível ler a aba ARQUIVOS do índice. Erro: {e}")
    st.stop()

ativos = [r for r in rows_arqs if str(r.get("ATIVO","S")).strip().upper() in {"S","SIM","Y","YES","TRUE","1"}]
if len(ativos) == 0:
    st.error("Planilha-índice vazia (aba ARQUIVOS).")
    st.stop()

dfs = []
falhas = []
for r in ativos:
    sid = _sheet_id(r.get("URL",""))
    ym  = _ym_token(r.get("MÊS") or r.get("MES"))
    if not sid:
        continue
    try:
        data_rows = read_sheet_records_by_key(sid, None)  # sheet1
        data = pd.DataFrame(data_rows)
        if data.empty:
            continue

        # padronização básica
        data.columns = [c.strip() for c in data.columns]
        if "empresa" in data.columns:
            data["empresa"] = (data["empresa"].astype(str).str.upper().str.strip().str.replace(r"\s+"," ",regex=True))
        if "unidade" in data.columns:
            data["unidade"] = (data["unidade"].astype(str).str.upper().str.strip().str.replace(r"\s+"," ",regex=True))

        # data
        date_candidates = [c for c in ["data_relatorio","DATA","Data","data"] if c in data.columns]
        date_col = date_candidates[0] if date_candidates else None
        data["__data__"] = data[date_col].apply(parse_date_value) if date_col else pd.NaT

        # deduz YM se faltar
        if ym is None and data["__data__"].notna().any():
            d = max([d for d in data["__data__"] if pd.notna(d)])
            ym = f"{d.year}-{d.month:02d}"
        data["__ym__"] = ym

        # números
        for col in ["total","revistorias","%_190","qtd_152","qtd_190"]:
            if col not in data.columns:
                data[col] = 0
            data[col] = pd.to_numeric(data[col], errors="coerce").fillna(0)

        dfs.append(data)
    except Exception as e:
        falhas.append((r.get("MÊS") or r.get("MES") or ym or "?", str(e)))
        # segue o loop

if falhas:
    st.warning("Algumas planilhas foram ignoradas por erro transitório:\n" +
               "\n".join([f"- Mês {m}: {err}" for m, err in falhas]))

if not dfs:
    st.error("Nenhuma planilha de mês pôde ser lida.")
    st.stop()

df = pd.concat(dfs, ignore_index=True)

# 👉 Merge: RIACHÃO → BALSAS
UNIDADE_MERGE_MAP = {"RIACHÃO":"BALSAS","RIACHAO":"BALSAS"}
if "unidade" in df.columns:
    df["unidade"] = df["unidade"].replace(UNIDADE_MERGE_MAP)

# --- METAS (aba METAS) ---
try:
    metas_rows = read_sheet_records_by_key(INDEX_SHEET_ID, INDEX_TAB_METAS)
except Exception:
    metas_rows = []

meta_map = {}  # (ym, EMPRESA, UNIDADE) -> (dias_uteis, meta_mensal)
for r in metas_rows:
    ym = _ym_token(r.get("MÊS") or r.get("MES"))
    emp = str(r.get("EMPRESA","")).strip().upper()
    uni = str(r.get("UNIDADE","")).strip().upper()
    if not ym or not emp or not uni:
        continue
    du  = r.get("DIAS_UTEIS", "")
    mm  = r.get("META_MENSAL", "")
    try: du = int(du) if str(du).strip() != "" else None
    except: du = None
    try: mm = int(mm) if str(mm).strip() != "" else None
    except: mm = None
    meta_map[(ym, emp, uni)] = (du, mm)

# =================== FUNÇÕES DE META (usam METAS da aba) ===================
def meta_unidade_mes(empresa: str, unidade: str, ym: str) -> int:
    base = int(metas_unidades_base.get(empresa, {}).get(unidade, 0))
    du, mm = meta_map.get((ym, empresa, unidade), (None, None))
    if mm is not None:
        return int(mm)
    du = du if du is not None else BASE_21
    return int(round(base * (du/BASE_21)))

def dias_uteis_unidade(empresa: str, unidade: str, ym: str) -> int:
    du, _ = meta_map.get((ym, empresa, unidade), (None, None))
    return int(du) if du else BASE_21

def meta_marca_mes(empresa: str, ym: str) -> int:
    unis = metas_unidades_base.get(empresa, {}).keys()
    return sum(meta_unidade_mes(empresa, u, ym) for u in unis)

# =================== HISTÓRICO COMPLETO ===================
df_full = df.copy()

# =================== SIDEBAR ===================
st.sidebar.header("📅 Dias úteis do mês")
dias_uteis_total = int(st.sidebar.slider("Dias úteis no mês (referência geral)", 1, 31, 21, step=1, key="dias_total"))
dias_uteis_passados = int(st.sidebar.slider("Dias úteis já passados", 0, 31, 16, step=1, key="dias_passados"))

dias_uteis_restantes = max(dias_uteis_total - dias_uteis_passados, 0)
mes_encerrado = (dias_uteis_restantes == 0)

# --- Sidebar: mês e dia ---
st.sidebar.markdown("---")
st.sidebar.subheader("🗓️ Período")

datas_validas = sorted([d for d in df_full["__data__"] if pd.notna(d)])
if not datas_validas:
    st.sidebar.info("Sem coluna de data reconhecida. Exibindo tudo.")
    df_view = df_full.copy()
    daily_mode, chosen_date = False, None
    ym_ref = df_full["__ym__"].dropna().iloc[-1] if df_full["__ym__"].notna().any() else None
else:
    meses = sorted({(d.year, d.month) for d in datas_validas})
    labels = [f"{mm:02d}/{yy}" for (yy, mm) in [(y, m) for (y, m) in meses]]
    mes_idx_default = len(labels) - 1
    mes_label = st.sidebar.selectbox("Mês de referência", options=labels, index=mes_idx_default)

    mm_sel, yy_sel = mes_label.split("/")
    ref_year, ref_month = int(yy_sel), int(mm_sel)

    mask_mes = df_full["__data__"].apply(lambda d: isinstance(d, date) and d.year == ref_year and d.month == ref_month)
    dias_mes = sorted([d for d in df_full.loc[mask_mes, "__data__"].unique() if pd.notna(d)])

    escolha = st.sidebar.selectbox(
        "Data do relatório",
        options=["(Mês inteiro)"] + [d.strftime("%d/%m/%Y") for d in dias_mes],
        index=0
    )

    if escolha == "(Mês inteiro)":
        df_view = df_full[mask_mes].copy()
        daily_mode, chosen_date = False, None
    else:
        chosen_date = datetime.strptime(escolha, "%d/%m/%Y").date()
        df_view = df_full[df_full["__data__"] == chosen_date].copy()
        daily_mode = True

    ym_ref = f"{ref_year}-{ref_month:02d}"

# ======== empresa/marca ========
empresas = sorted(df_view['empresa'].dropna().unique())
if len(empresas) == 0:
    st.warning("Não há dados para exibir. Verifique as planilhas.")
    st.stop()

# >>> alteração 2: trava marca quando BRAND_SCOPE != ALL
if BRAND_SCOPE == "ALL":
    empresa_selecionada = st.selectbox("Selecione a Marca:", empresas)
else:
    empresa_selecionada = BRAND_SCOPE
    if empresa_selecionada not in empresas:
        st.error(f"Não há dados para a marca '{empresa_selecionada}'.")
        st.stop()
    st.info(f"Visualização fixa para a marca **{empresa_selecionada}**")

df_filtrado = df_view[df_view['empresa'] == empresa_selecionada].copy()
df_marca_all = df_full[df_full["empresa"] == empresa_selecionada].copy()

# mês de referência para metas
if 'daily_mode' in locals() and daily_mode and 'chosen_date' in locals() and chosen_date:
    ym_ref = f"{chosen_date.year}-{chosen_date.month:02d}"
elif df_filtrado["__ym__"].notna().any():
    ym_ref = df_filtrado["__ym__"].dropna().iloc[-1]
else:
    ym_ref = df_full["__ym__"].dropna().iloc[-1]

# =================== CONSOLIDADO (MARCA) ===================
meta_mes_marca = meta_marca_mes(empresa_selecionada, ym_ref)
total_geral_marca = int(df_filtrado['total'].sum())
total_rev_marca   = int(df_filtrado['revistorias'].sum())
total_liq_marca   = total_geral_marca - total_rev_marca

if 'daily_mode' in locals() and daily_mode:
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
    necessidade_por_dia = 0 if mes_encerrado else int(safe_div(faltante_marca, dias_uteis_restantes))
    cards = [
        ("Meta da Marca", meta_mes_marca),
        ("Total Geral", total_geral_marca),
        ("Total Revistorias", total_rev_marca),
        ("Total Líquido", total_liq_marca),
        ("Faltante", faltante_marca),
        ("Necessidade/dia", necessidade_por_dia),
        ("Projeção (Fim do mês)", int(projecao_marca_total)),
        ("Tendência", f"{tendencia:.0f}% {'🚀' if tendencia >= 100 else '😟'}"),
    ]

st.markdown("""
<style>
.card-container{display:flex;gap:20px;margin-bottom:30px;flex-wrap:wrap;}
.card{background:#f5f5f5;padding:20px;border-radius:12px;box-shadow:0 2px 6px rgba(0,0,0,.1);text-align:center;min-width:170px;flex:1;}
.card h4{color:#cc3300;margin:0 0 8px;font-size:16px;}
.card h2{margin:0;font-size:26px;font-weight:bold;color:#222;}
.section-title{font-size:20px;font-weight:700;margin:18px 0 8px;}
</style>
""", unsafe_allow_html=True)

st.markdown(f"### 🏢 Consolidado - {empresa_selecionada}")
st.markdown("<div class='card-container'>" + "".join([f"<div class='card'><h4>{t}</h4><h2>{v}</h2></div>" for t,v in cards]) + "</div>", unsafe_allow_html=True)

# =================== TABELA POR UNIDADE ===================
st.subheader("📍 Indicadores por Unidade")

# MTD no modo dia (para projeção)
mtd_liq_by_unit = {}
if 'daily_mode' in locals() and daily_mode and 'chosen_date' in locals() and chosen_date is not None:
    mask_mtd = df_marca_all["__data__"].apply(lambda d: isinstance(d, date) and d.year==chosen_date.year and d.month==chosen_date.month and d<=chosen_date)
    df_mtd = df_marca_all[mask_mtd & (df_marca_all["empresa"] == empresa_selecionada)]
    if len(df_mtd):
        grp_mtd = (df_mtd.groupby("unidade", dropna=False, as_index=False)
                        .agg(total=("total","sum"), rev=("revistorias","sum")))
        grp_mtd["liq"] = (grp_mtd["total"] - grp_mtd["rev"]).astype(int)
        mtd_liq_by_unit = dict(zip(grp_mtd["unidade"], grp_mtd["liq"]))

# >>> AGRUPAMENTO COM TICKET CORRETO (ponderado por qtd_152 e qtd_190)
agr = df_filtrado.groupby("unidade", dropna=False, as_index=False).agg(
    total=("total","sum"),
    rev=("revistorias","sum"),
    qtd152=("qtd_152","sum"),
    qtd190=("qtd_190","sum"),
    pct190=("%_190","mean")
)

def calc_ticket(q152, q190):
    q152 = float(q152); q190 = float(q190)
    denom = q152 + q190
    return (q152*152.0 + q190*190.0)/denom if denom > 0 else np.nan

linhas = []
for _, r in agr.iterrows():
    unidade = r["unidade"]
    total = int(r["total"]); rev = int(r["rev"]); liq = total - rev

    meta_mes = meta_unidade_mes(empresa_selecionada, unidade, ym_ref)

    if 'daily_mode' in locals() and daily_mode:
        du_unit = dias_uteis_unidade(empresa_selecionada, unidade, ym_ref)
        meta_dia = safe_div(meta_mes, du_unit)
        faltante = max(int(round(meta_dia)) - liq, 0)
        tendencia_u = safe_div(liq, meta_dia) * 100 if meta_dia else 0
        tendencia_txt = f"{tendencia_u:.0f}% {'🚀' if tendencia_u >= 100 else '😟'}"
        meta_col = int(round(meta_dia))
        falt_label = "Faltante (Dia)"
        nec_dia = faltante
        total_label = "Total (Dia)"; rev_label = "Revistorias (Dia)"; liq_label = "Total Líquido (Dia)"; tend_label = "Tendência (Dia)"
        mtd_liq_u = int(mtd_liq_by_unit.get(unidade, liq))
        media_u = safe_div(mtd_liq_u, dias_uteis_passados) if dias_uteis_passados else 0
        proj_col = int(round(mtd_liq_u + media_u * dias_uteis_restantes))
    else:
        faltante = max(meta_mes - liq, 0)
        media = safe_div(liq, dias_uteis_passados)
        proj_final = liq + media * dias_uteis_restantes
        tendencia_u = safe_div(proj_final, meta_mes) * 100 if meta_mes else 0
        tendencia_txt = f"{tendencia_u:.0f}% {'🚀' if tendencia_u >= 100 else '😟'}"
        meta_col = meta_mes
        falt_label = "Faltante (sobre Líquido)"
        nec_dia = 0 if mes_encerrado else safe_div(faltante, dias_uteis_restantes)
        total_label = "Total"; rev_label = "Revistorias"; liq_label = "Total Líquido"; tend_label = "Tendência"
        proj_col = int(round(proj_final))

    # ticket médio ponderado pelo mix 152/190
    ticket_val = calc_ticket(r["qtd152"], r["qtd190"])
    ticket_txt = "—"
    if not np.isnan(ticket_val):
        ticket_txt = f"R$ {ticket_val:.2f} " + ("✅" if ticket_val >= 161.50 else "❌")

    pct190 = float(r["pct190"]); icon_190 = "✅" if pct190 >= 25 else ("⚠️" if pct190 >= 20 else "❌")

    linhas.append({
        "Unidade": unidade,
        "Meta do Dia" if ('daily_mode' in locals() and daily_mode) else "Meta": int(meta_col),
        total_label: total, rev_label: rev, liq_label: liq,
        falt_label: int(faltante),
        "Necessidade/dia": int(nec_dia) if ('daily_mode' in locals() and daily_mode) else round(nec_dia, 1),
        tend_label: tendencia_txt,
        "Projeção (Mês)": proj_col,
        "Ticket Médio (R$)": ticket_txt,
        "% ≥ R$190": f"{pct190:.0f}% {icon_190}"
    })

# --- Normalização de chaves para evitar KeyError no gráfico ---
for r in linhas:
    # Total Líquido
    if "Total Líquido (Dia)" in r and "Total Líquido" not in r:
        r["Total Líquido"] = r["Total Líquido (Dia)"]
    if "Total Líquido" in r and "Total Líquido (Dia)" not in r:
        r["Total Líquido (Dia)"] = r["Total Líquido"]
    # Total
    if "Total (Dia)" in r and "Total" not in r:
        r["Total"] = r["Total (Dia)"]
    if "Total" in r and "Total (Dia)" not in r:
        r["Total (Dia)"] = r["Total"]
    # Revistorias
    if "Revistorias (Dia)" in r and "Revistorias" not in r:
        r["Revistorias"] = r["Revistorias (Dia)"]
    if "Revistorias" in r and "Revistorias (Dia)" not in r:
        r["Revistorias (Dia)"] = r["Revistorias"]

tabela_unidades_df = pd.DataFrame(linhas)
st.dataframe(tabela_unidades_df, use_container_width=True)

# =================== GRÁFICO (matplotlib) ===================
st.subheader("📊 Produção Realizada por Unidade " + ("(Líquido - Dia)" if ('daily_mode' in locals() and daily_mode) else "(Líquido)"))
unidades = [d.get("Unidade", "—") for d in linhas]

# Blindagem: tenta pegar a métrica do contexto e cai para a outra chave se necessário
prod_liq = []
for dct in linhas:
    if 'daily_mode' in locals() and daily_mode:
        val = dct.get("Total Líquido (Dia)", dct.get("Total Líquido", 0))
    else:
        val = dct.get("Total Líquido", dct.get("Total Líquido (Dia)", 0))
    prod_liq.append(int(val) if pd.notna(val) else 0)

fig, ax = plt.subplots(figsize=(10,5))
barras = ax.bar(unidades, prod_liq)
for b in barras:
    h = b.get_height()
    ax.annotate(f'{int(h)}', xy=(b.get_x()+b.get_width()/2, h), xytext=(0,5),
                textcoords="offset points", ha='center', va='bottom', fontsize=10, fontweight='bold')
plt.xticks(rotation=0 if len(unidades) <= 8 else 30)
ax.set_ylabel("Produção (Líquido)"); ax.set_xlabel("Unidade")
ax.set_title("Produção por Unidade" + (" - Dia" if ('daily_mode' in locals() and daily_mode) else ""))
st.pyplot(fig)

# =================== CONSOLIDADO GERAL (apenas no app ALL) ===================
# >>> alteração 3: esconder quando BRAND_SCOPE != ALL
if BRAND_SCOPE == "ALL":
    st.markdown("---")
    st.markdown("## 🏢 Consolidado Geral - Total das 4 Marcas")

    agg_geral = df_view.groupby("empresa", dropna=False).agg(total=("total","sum"), rev=("revistorias","sum")).reset_index()
    real_total = int(agg_geral["total"].sum())
    rev_total  = int(agg_geral["rev"].sum())
    liq_total  = int(real_total - rev_total)

    meta_mes_geral = sum(meta_marca_mes(m, ym_ref) for m in metas_unidades_base.keys())

    if 'daily_mode' in locals() and daily_mode:
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
        necessidade_g = 0 if mes_encerrado else int(safe_div(falt_geral, dias_uteis_restantes))
        geral_cards = [
            ("Meta Geral", meta_mes_geral), ("Total Geral", real_total), ("Total Revistorias", rev_total),
            ("Total Líquido", liq_total), ("Faltante", falt_geral),
            ("Necessidade/dia", necessidade_g),
            ("Projeção (Fim do mês)", int(proj_g_total)), ("Tendência", f"{tendencia_g:.0f}% {'🚀' if tendencia_g >= 100 else '😟'}"),
        ]

    st.markdown("<div class='card-container'>" + "".join([f"<div class='card'><h4>{t}</h4><h2>{v}</h2></div>" for t,v in geral_cards]) + "</div>", unsafe_allow_html=True)

# =================== HEATMAP ===================
st.markdown("---")
st.markdown("<div class='section-title'>📅 Heatmap do Mês (Calendário)</div>", unsafe_allow_html=True)

HEAT_W, HEAT_H = 980, 420
MIN_PCT = 60

datas_marca = sorted([d for d in df_marca_all["__data__"].unique() if pd.notna(d)])
if datas_marca:
    last_date = datas_marca[-1]
    months_available = sorted({(d.year, d.month) for d in datas_marca})
    month_labels = [f"{y}-{m:02d}" for (y,m) in months_available]
    default_month = f"{last_date.year}-{last_date.month:02d}"
    default_idx = month_labels.index(default_month) if default_month in month_labels else len(month_labels)-1
    month_choice = st.selectbox("Mês de referência (marca)", options=month_labels, index=default_idx, key="mes_heatmap")
    ref_year, ref_month = map(int, month_choice.split("-"))
else:
    today = date.today()
    ref_year, ref_month = today.year, today.month

unidades_da_marca = sorted([u for u in df_marca_all["unidade"].dropna().unique().tolist()])
unidade_heat = st.selectbox("Escopo do heatmap", options=["(Consolidado da Marca)"] + unidades_da_marca, index=0, key="heatmap_unidade")

if unidade_heat == "(Consolidado da Marca)":
    df_heat_src = df_marca_all.copy()
    meta_mes_ref = meta_marca_mes(empresa_selecionada, f"{ref_year}-{ref_month:02d}")
    titulo_escopo = empresa_selecionada
else:
    df_heat_src = df_marca_all[df_marca_all["unidade"] == unidade_heat].copy()
    meta_mes_ref = meta_unidade_mes(empresa_selecionada, unidade_heat, f"{ref_year}-{ref_month:02d}")
    titulo_escopo = f"{empresa_selecionada} — {unidade_heat}"

mask_month = df_heat_src["__data__"].apply(lambda d: isinstance(d, date) and d.year==ref_year and d.month==ref_month)
df_month = df_heat_src[mask_month].copy()

if len(df_month) > 0:
    tmp = (df_month.groupby("__data__", as_index=False).agg(total=("total","sum"), rev=("revistorias","sum")))
    tmp["liq"] = (tmp["total"] - tmp["rev"]).astype(int)
    daily_liq = tmp[["__data__","liq"]]
    last_data_day = daily_liq["__data__"].max()
else:
    daily_liq = pd.DataFrame(columns=["__data__","liq"]); last_data_day = None

metric_choice = st.radio("Cor do heatmap baseada em:", ["% da meta do dia","Total Líquido"], horizontal=True, key="heatmap_metric")
show_values = st.checkbox("Mostrar valor dentro das células", value=False, key="heatmap_labels")

meta_dia_base = (meta_mes_ref / dias_uteis_total) if dias_uteis_total else 0

first_weekday, n_days = calendar.monthrange(ref_year, ref_month)
liq_map = daily_liq.set_index("__data__")["liq"].to_dict()

records = []
ord_dow = ["Seg","Ter","Qua","Qui","Sex","Sáb","Dom"]
for day in range(1, n_days+1):
    d0 = date(ref_year, ref_month, day)
    if (last_data_day is None) or (d0 > last_data_day) or (d0 not in liq_map):
        liq = np.nan
    else:
        liq = float(liq_map[d0])
    pct = (liq / meta_dia_base * 100) if (not np.isnan(liq) and meta_dia_base) else np.nan
    dow_idx = d0.weekday()
    dow_label = ord_dow[dow_idx]
    week_index = (day + first_weekday - 1)//7
    if metric_choice == "% da meta do dia":
        value = pct if (not np.isnan(pct) and dow_idx < 5) else np.nan
        val_label_str = f"{pct:.0f}%" if (show_values and not np.isnan(pct) and dow_idx < 5) else ""
    else:
        value = liq if not np.isnan(liq) else np.nan
        val_label_str = f"{int(liq)}" if (show_values and not np.isnan(liq)) else ""
    records.append({"date": pd.to_datetime(d0), "day": day, "dow_label": dow_label, "week_index": week_index,
                    "liq": liq, "pct": pct, "value": value, "val_label_str": val_label_str})

cal_df = pd.DataFrame.from_records(records)

base = alt.Chart(cal_df).properties(width=HEAT_W, height=HEAT_H)
color_scale = alt.Scale(scheme='viridis', domain=[MIN_PCT, 120], clamp=True) if metric_choice=="% da meta do dia" else alt.Scale(scheme='viridis')
color_title = '%' if metric_choice=="% da meta do dia" else 'Líquido'

heat = base.mark_rect().encode(
    x=alt.X('dow_label:N', title='', scale=alt.Scale(domain=ord_dow)),
    y=alt.Y('week_index:O', title='', sort=alt.SortField('week_index', order='ascending'), axis=None),
    color=alt.Color('value:Q', title=color_title, scale=color_scale),
    tooltip=[alt.Tooltip('date:T', title='Data'),
             alt.Tooltip('liq:Q',  title='Líquido', format='.0f'),
             alt.Tooltip('pct:Q',  title='% Meta',  format='.0f')]
)
labels_day = base.mark_text(baseline='middle', dy=-8, fontSize=12, color='black').encode(x='dow_label:N', y='week_index:O', text='day:Q')
chart = heat + labels_day
if show_values:
    labels_val = base.mark_text(baseline='middle', dy=10, fontSize=11, color='white',
                                stroke='white', strokeWidth=0.8).encode(x='dow_label:N', y='week_index:O', text='val_label_str:N')
    chart = chart + labels_val

max_week = int(cal_df["week_index"].max()) if len(cal_df) else 5
grid_records = [{"dow_label": d, "week_index": w} for w in range(max_week+1) for d in ord_dow]
grid_df = pd.DataFrame(grid_records)
grid = alt.Chart(grid_df).mark_rect(stroke="#E6E6E6", strokeWidth=1, fillOpacity=0).encode(
    x=alt.X('dow_label:N', title='', scale=alt.Scale(domain=ord_dow)),
    y=alt.Y('week_index:O', title='', sort=alt.SortField('week_index', order='ascending'), axis=None)
).properties(width=HEAT_W, height=HEAT_H)

st.altair_chart(grid + chart, use_container_width=False)
st.caption(f"Escopo: {empresa_selecionada if unidade_heat=='(Consolidado da Marca)' else f'{empresa_selecionada} — {unidade_heat}'}")

# =================== CATCH-UP ===================
st.markdown("<div class='section-title'>📋 Acompanhamento Diário com Meta Ajustada (Catch-up)</div>", unsafe_allow_html=True)

unidades_marca = ["(Consolidado da Marca)"] + sorted(df_marca_all["unidade"].dropna().unique().tolist())
un_sel = st.selectbox("Unidade", options=unidades_marca, index=0, key="un_meta_tab")

mask_month_brand = df_marca_all["__data__"].apply(lambda d: isinstance(d, date) and d.year==ref_year and d.month==ref_month)
df_month_brand = df_marca_all[mask_month_brand].copy()
if un_sel != "(Consolidado da Marca)":
    df_month_brand = df_month_brand[df_month_brand["unidade"] == un_sel]

daily_series = (df_month_brand.groupby("__data__").apply(lambda x: int(x["total"].sum() - x["revistorias"].sum())).sort_index())

if un_sel == "(Consolidado da Marca)":
    meta_mes_ref = meta_marca_mes(empresa_selecionada, f"{ref_year}-{ref_month:02d}")
    du_ref = dias_uteis_total
else:
    meta_mes_ref = meta_unidade_mes(empresa_selecionada, un_sel, f"{ref_year}-{ref_month:02d}")
    du_ref = dias_uteis_unidade(empresa_selecionada, un_sel, f"{ref_year}-{ref_month:02d}")

meta_dia_const = safe_div(meta_mes_ref, du_ref)

month_start = date(ref_year, ref_month, 1)
month_end   = date(ref_year, ref_month, calendar.monthrange(ref_year, ref_month)[1])
all_days = pd.date_range(month_start, month_end, freq="D")
workdays_dates = [ts.date() for ts in all_days if is_workday(ts.date())]

remaining_map = {wd: (len(workdays_dates)-i) for i, wd in enumerate(workdays_dates)}

rows = []
acum_real = 0
for d0, liq in daily_series.items():
    if d0 in remaining_map:
        meta_dia_ajustada = safe_div((meta_mes_ref - acum_real), remaining_map[d0])
    else:
        meta_dia_ajustada = 0
    diff_dia = liq - meta_dia_ajustada
    acum_real += liq
    saldo_restante = meta_mes_ref - acum_real
    rows.append({
        "Data": d0.strftime("%d/%m/%Y"),
        "Meta (constante)": round(meta_dia_const, 1),
        "Meta Ajustada (catch-up)": round(meta_dia_ajustada, 1),
        "Realizado Líquido": int(liq),
        "Δ do Dia (Real − Meta Aj.)": round(diff_dia, 1),
        "Acumulado Líquido": int(acum_real),
        "Saldo p/ Bater Meta": int(saldo_restante),
        "Status": "✅" if liq >= meta_dia_ajustada and meta_dia_ajustada > 0 else ("—" if meta_dia_ajustada == 0 else "❌")
    })
st.dataframe(pd.DataFrame(rows), use_container_width=True)

# =================== RANKING DIÁRIO ===================
st.markdown("<div class='section-title'>🏆 Ranking Diário por Unidade (Tendência do Dia e Variação vs Ontem)</div>", unsafe_allow_html=True)

if 'daily_series' in locals() and len(daily_series):
    if 'daily_mode' in locals() and daily_mode and 'chosen_date' in locals() and chosen_date and (chosen_date.year==ref_year and chosen_date.month==ref_month):
        rank_date = chosen_date
    else:
        rank_date = max(daily_series.index) if len(daily_series) else None
else:
    rank_date = None

if rank_date is None:
    st.info("Ainda não há dados neste mês para montar o ranking.")
else:
    df_unit_daily = (df_marca_all
        .groupby(["unidade","__data__"])
        .apply(lambda x: int(x["total"].sum() - x["revistorias"].sum()))
        .rename("liq").reset_index())

    today_df = df_unit_daily[df_unit_daily["__data__"] == rank_date].copy()

    def last_workday_with_data(u):
        prevs = df_unit_daily[(df_unit_daily["unidade"] == u) & (df_unit_daily["__data__"] < rank_date)]
        prevs = prevs[prevs["__data__"].apply(is_workday)]
        if len(prevs) == 0: return None, 0
        row = prevs.sort_values("__data__").iloc[-1]
        return row["__data__"], row["liq"]

    prev_map = []
    for u in today_df["unidade"].unique():
        dprev, liqprev = last_workday_with_data(u)
        prev_map.append({"unidade": u, "__data_prev__": dprev, "liq_prev": liqprev})
    prev_df = pd.DataFrame(prev_map)

    metas_u = []
    for u in today_df["unidade"].unique():
        metas_u.append({"unidade": u, "meta_mes": meta_unidade_mes(empresa_selecionada, u, ym_ref),
                        "du": dias_uteis_unidade(empresa_selecionada, u, ym_ref)})
    metas_u = pd.DataFrame(metas_u)

    df_rank = (today_df.merge(prev_df, on="unidade", how="left").merge(metas_u, on="unidade", how="left"))
    df_rank["meta_dia"] = np.where(df_rank["du"]>0, df_rank["meta_mes"]/df_rank["du"], 0)

    workday_rank = is_workday(rank_date)
    df_rank["pct_hoje"] = np.where(df_rank["meta_dia"]>0, (df_rank["liq"]/df_rank["meta_dia"])*100, 0.0)
    df_rank["pct_ontem"] = np.where((df_rank["meta_dia"]>0) & df_rank["__data_prev__"].notna(),
                                    (df_rank["liq_prev"]/df_rank["meta_dia"])*100, np.nan)
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
            linhas_rank = []
            for _, r in df_sub.iterrows():
                linhas_rank.append({
                    "Unidade": r["unidade"],
                    "% do Dia": f"{r['pct_hoje']:.0f}%" if workday_rank else "—",
                    "Δ vs Ontem": fmt_delta(r["delta_pct"]) if workday_rank else "—",
                    "Líquido (Dia)": int(r["liq"]),
                    "Meta do Dia": int(round(r["meta_dia"])) if (workday_rank and r["meta_dia"]>0) else 0
                })
            st.dataframe(pd.DataFrame(linhas_rank), use_container_width=True)

    render_rank(df_rank.head(5), "TOP 5", col1)
    render_rank(df_rank.tail(5).sort_values(order_col, ascending=True), "BOTTOM 5", col2)
