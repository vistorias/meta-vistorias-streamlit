import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ========= Configuração básica =========
st.set_page_config(layout="wide", page_title="Acompanhamento de Meta Mensal - Vistorias")
st.title("📊 Acompanhamento de Meta Mensal - Vistorias")

st.markdown("""
<div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
    <h4 style="color: #cc3300; margin: 0;">👋 Bem-vindo(a) ao Painel de Acompanhamento de Metas!</h4>
    <p style="margin: 5px 0 0 0;">Aqui você pode acompanhar em tempo real a performance das unidades e identificar oportunidades de melhoria com base nas metas do mês. Use os filtros à esquerda para ajustar os dados conforme o período desejado.</p>
</div>
""", unsafe_allow_html=True)

# ========= Conectar ao Google Sheets =========
# Observação: mantenha suas credenciais no st.secrets["gcp_service_account"]
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# ID da planilha (não mude se já estiver correto)
SHEET_KEY = "1ooMhPk-R-Etzut4BHkxCTgYZx8fztHzDlhyXuS9TLGo"

# Carregar dados
sheet = client.open_by_key(SHEET_KEY).sheet1
data = sheet.get_all_records()
df = pd.DataFrame(data)

# ========= Padronizações e conversões =========
# Nomes de colunas esperadas:
# - empresa
# - unidade
# - total            (produção bruta do dia/acumulado)
# - revistorias      (quantidade de revistorias)
# - ticket_medio     (em centavos ou inteiro, como no seu painel anterior)
# - %_190            (percentual de atendimentos >= R$ 190 – numérico)
# - data_relatorio   (nova coluna com a data do relatório diário)

# Upper em textos
if "empresa" in df.columns:
    df["empresa"] = df["empresa"].astype(str).str.upper()
if "unidade" in df.columns:
    df["unidade"] = df["unidade"].astype(str).str.upper()

# Converte numéricos
for col in ["total", "revistorias", "ticket_medio", "%_190"]:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

# Ticket médio em reais (mantendo a lógica anterior de dividir por 100)
if "ticket_medio" in df.columns:
    df["ticket_medio_real"] = df["ticket_medio"] / 100
else:
    df["ticket_medio_real"] = 0

# %_190 como inteiro para exibição
if "%_190" not in df.columns:
    df["%_190"] = 0

# Revistorias (se não existir, assume 0 para manter compatibilidade)
if "revistorias" not in df.columns:
    df["revistorias"] = 0

# Data do relatório
if "data_relatorio" in df.columns:
    # Tenta converter automaticamente datas no formato brasileiro ou ISO
    def parse_date(x):
        if pd.isna(x) or x == "":
            return pd.NaT
        # Se vier como número (Sheets), tenta converter por epoch excel (não obrigatório normalmente)
        if isinstance(x, (int, float)):
            # Fallback: trata como serial do Excel (pouco comum nessa base)
            try:
                return pd.to_datetime('1899-12-30') + pd.to_timedelta(int(x), unit='D')
            except:
                return pd.NaT
        # Strings comuns: "dd/mm/aaaa" ou "aaaa-mm-dd"
        for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(str(x), fmt).date()
            except:
                pass
        # Último recurso
        try:
            return pd.to_datetime(x).date()
        except:
            return pd.NaT

    df["data_relatorio"] = df["data_relatorio"].apply(parse_date)
else:
    # Se não existir, cria vazia (sem filtro de data)
    df["data_relatorio"] = pd.NaT

# ========= Metas (mantida sua estrutura) =========
metas_unidades = {
    "TOKYO": {"BARRA DO CORDA": 650, "CHAPADINHA": 550, "SANTA INÊS": 2200, "SÃO JOÃO DOS PATOS": 435, "SÃO JOSÉ DE RIBAMAR": 2000},
    "STARCHECK": {"BACABAL": 1640, "BALSAS": 1505, "CAXIAS": 560, "CODÓ": 380, "PINHEIRO": 900, "SÃO LUÍS": 3200},
    "LOG": {"AÇAILÂNDIA": 1100, "CAROLINA": 135, "PRESIDENTE DUTRA": 875, "SÃO LUÍS": 4240, "TIMON": 980},
    "VELOX": {"ESTREITO": 463, "GRAJAÚ": 500, "IMPERATRIZ": 3350, "PEDREIRAS": 600, "SÃO LUÍS": 1850}
}
metas_gerais = {"TOKYO": 5835, "STARCHECK": 8305, "LOG": 7330, "VELOX": 6763}

# ========= Filtros (barra lateral) =========
st.sidebar.header("📅 Dias úteis do mês")
dias_uteis_total = st.sidebar.number_input("Dias úteis no mês", 1, 31, 21)
dias_uteis_passados = st.sidebar.number_input("Dias úteis já passados", 0, 31, 16)
dias_uteis_restantes = max(dias_uteis_total - dias_uteis_passados, 1)

# Filtro por data (ao lado dos dias úteis)
st.sidebar.markdown("---")
st.sidebar.subheader("🗓️ Filtro por Data do Relatório")
tem_data = df["data_relatorio"].notna().any()
if tem_data:
    datas_validas = sorted([d for d in df["data_relatorio"].unique() if pd.notna(d)])
    data_default = datas_validas[-1] if len(datas_validas) > 0 else None
    data_escolhida = st.sidebar.selectbox("Data do relatório", options=["(Mês inteiro)"] + [str(d) for d in datas_validas],
                                          index=0 if data_default is None else datas_validas.index(data_default) + 1)
    if data_escolhida != "(Mês inteiro)":
        data_dt = pd.to_datetime(data_escolhida).date()
        df = df[df["data_relatorio"] == data_dt]
else:
    st.sidebar.info("Sua base ainda não possui a coluna **data_relatorio** ou está vazia. Exibindo mês inteiro.")

# ========= Filtro de empresa =========
empresas = sorted(df['empresa'].dropna().unique())
if len(empresas) == 0:
    st.warning("Não há dados para exibir. Verifique a planilha.")
    st.stop()

empresa_selecionada = st.selectbox("Selecione a Marca:", empresas)
df_filtrado = df[df['empresa'] == empresa_selecionada].copy()

# ========= Consolidado da marca =========
meta_marca = metas_gerais.get(empresa_selecionada, 0)
total_geral_marca = int(df_filtrado['total'].sum())
total_rev_marca = int(df_filtrado['revistorias'].sum())
total_liquido_marca = int(total_geral_marca - total_rev_marca)

faltante_marca = max(meta_marca - total_liquido_marca, 0)

media_diaria = total_liquido_marca / dias_uteis_passados if dias_uteis_passados else 0
projecao_marca = media_diaria * dias_uteis_total
tendencia_marca = (projecao_marca / meta_marca * 100) if meta_marca else 0
icone_tendencia = "🚀" if tendencia_marca >= 100 else "😟"
necessidade_dia_marca = (faltante_marca / dias_uteis_restantes) if dias_uteis_restantes else 0

# ========= Cartões (estilo) =========
st.markdown("""
<style>
.card-container {
  display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap;
}
.card {
  background-color: #f5f5f5; padding: 20px; border-radius: 12px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.1); text-align: center;
  min-width: 170px; flex: 1;
}
.card h4 {
  color: #cc3300; margin: 0 0 8px; font-size: 16px;
}
.card h2 {
  margin: 0; font-size: 26px; font-weight: bold; color: #222;
}
</style>
""", unsafe_allow_html=True)

# ========= Cartões da marca =========
st.markdown("### 🏢 Consolidado - " + empresa_selecionada)
st.markdown(f"""
<div class="card-container">
  <div class="card"><h4>Meta da Marca</h4><h2>{meta_marca}</h2></div>
  <div class="card"><h4>Total Geral</h4><h2>{total_geral_marca}</h2></div>
  <div class="card"><h4>Total Revistorias</h4><h2>{total_rev_marca}</h2></div>
  <div class="card"><h4>Total Líquido</h4><h2>{total_liquido_marca}</h2></div>
  <div class="card"><h4>Faltante</h4><h2>{faltante_marca}</h2></div>
  <div class="card"><h4>Necessidade/dia</h4><h2>{int(necessidade_dia_marca)}</h2></div>
  <div class="card"><h4>Projeção</h4><h2>{int(projecao_marca)}</h2></div>
  <div class="card"><h4>Tendência</h4><h2>{tendencia_marca:.0f}% {icone_tendencia}</h2></div>
</div>
""", unsafe_allow_html=True)

# ========= Tabela por unidade =========
st.subheader("📍 Indicadores por Unidade")

# Agrega por unidade (caso a planilha traga linhas diárias)
agrupado = df_filtrado.groupby("unidade", dropna=False, as_index=False).agg(
    total=("total", "sum"),
    revistorias=("revistorias", "sum"),
    ticket_medio_real=("ticket_medio_real", "mean"),
    pct190=("%_190", "mean")
)

dados = []
for _, row in agrupado.iterrows():
    unidade = row['unidade']
    realizado_total = int(row['total'])
    rev = int(row['revistorias'])
    liquido = realizado_total - rev

    meta = metas_unidades.get(empresa_selecionada, {}).get(unidade, 0)
    faltante = max(meta - liquido, 0)

    proj_dia = (faltante / dias_uteis_restantes) if dias_uteis_restantes else 0
    media = (liquido / dias_uteis_passados) if dias_uteis_passados else 0
    proj_final = media * dias_uteis_total
    tendencia = (proj_final / meta * 100) if meta else 0
    icone_tend = "🚀" if tendencia >= 100 else "😟"

    ticket = round(float(row['ticket_medio_real']), 2)
    icone_ticket = "✅" if ticket >= 161.50 else "❌"

    pct_190 = float(row['pct190'])
    icone_190 = "✅" if pct_190 >= 25 else "⚠️" if pct_190 >= 20 else "❌"

    dados.append({
        "Unidade": unidade,
        "Meta": int(meta),
        "Total": realizado_total,
        "Revistorias": rev,
        "Total Líquido": liquido,
        "Faltante (sobre Líquido)": int(faltante),
        "Necessidade/dia": round(proj_dia, 1),
        "Tendência": f"{tendencia:.0f}% {icone_tend}",
        "Ticket Médio (R$)": f"R$ {ticket:.2f} {icone_ticket}",
        "% ≥ R$190": f"{pct_190:.0f}% {icone_190}"
    })

st.dataframe(pd.DataFrame(dados), use_container_width=True)

# ========= Gráfico por unidade (usando Total Líquido) =========
st.subheader("📊 Produção Realizada por Unidade (Líquido)")

unidades = [d["Unidade"] for d in dados]
producoes_liquidas = [d["Total Líquido"] for d in dados]

fig, ax = plt.subplots(figsize=(10, 5))
barras = ax.bar(unidades, producoes_liquidas)
for barra in barras:
    altura = barra.get_height()
    ax.annotate(f'{int(altura)}', xy=(barra.get_x() + barra.get_width()/2, altura),
                xytext=(0, 5), textcoords="offset points",
                ha='center', va='bottom', fontsize=10, fontweight='bold')
plt.xticks(rotation=0)
ax.set_ylabel("Produção (Líquido)")
ax.set_xlabel("Unidade")
ax.set_title("Produção Líquida por Unidade")
st.pyplot(fig)

# ========= Consolidado Geral (todas as marcas) =========
st.markdown("---")
st.markdown("## 🏢 Consolidado Geral - Total das 4 Marcas")

# Agrega geral (após possível filtro de data)
df_agg_geral = df.groupby("empresa", dropna=False).agg(
    total=("total", "sum"),
    rev=("revistorias", "sum")
).reset_index()

realizado_geral_total = int(df_agg_geral["total"].sum())
revistorias_geral_total = int(df_agg_geral["rev"].sum())
liquido_geral_total = int(realizado_geral_total - revistorias_geral_total)

meta_geral = sum(metas_gerais.values())
faltante_geral = max(meta_geral - liquido_geral_total, 0)

media_geral = (liquido_geral_total / dias_uteis_passados) if dias_uteis_passados else 0
projecao_geral = media_geral * dias_uteis_total
tendencia_geral = (projecao_geral / meta_geral * 100) if meta_geral else 0
icone_geral = "🚀" if tendencia_geral >= 100 else "😟"
necessidade_dia_geral = (faltante_geral / dias_uteis_restantes) if dias_uteis_restantes else 0

st.markdown(f"""
<div class="card-container">
  <div class="card"><h4>Meta Geral</h4><h2>{meta_geral}</h2></div>
  <div class="card"><h4>Total Geral</h4><h2>{realizado_geral_total}</h2></div>
  <div class="card"><h4>Total Revistorias</h4><h2>{revistorias_geral_total}</h2></div>
  <div class="card"><h4>Total Líquido</h4><h2>{liquido_geral_total}</h2></div>
  <div class="card"><h4>Faltante</h4><h2>{faltante_geral}</h2></div>
  <div class="card"><h4>Necessidade/dia</h4><h2>{int(necessidade_dia_geral)}</h2></div>
  <div class="card"><h4>Projeção</h4><h2>{int(projecao_geral)}</h2></div>
  <div class="card"><h4>Tendência</h4><h2>{tendencia_geral:.0f}% {icone_geral}</h2></div>
</div>
""", unsafe_allow_html=True)
