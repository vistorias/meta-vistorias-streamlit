import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(layout="wide")
st.title("📊 Acompanhamento de Meta Mensal - Vistorias")

st.markdown("""
<div style="background-color: #f0f2f6; padding: 15px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);">
    <h4 style="color: #cc3300; margin: 0;">👋 Bem-vindo(a) ao Painel de Acompanhamento de Metas!</h4>
    <p style="margin: 5px 0 0 0;">Aqui você pode acompanhar em tempo real a performance das unidades e identificar oportunidades de melhoria com base nas metas do mês. Use os filtros à esquerda para ajustar os dados conforme o período desejado.</p>
</div>
""", unsafe_allow_html=True)

# 🔐 Conectar ao Google Sheets
import json  # adicione essa linha no início se ainda não tiver

scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# 📄 Carregar planilha
sheet = client.open_by_key("1ooMhPk-R-Etzut4BHkxCTgYZx8fztHzDlhyXuS9TLGo").sheet1
data = sheet.get_all_records()
df = pd.DataFrame(data)

# 🎯 Ajustes iniciais
df['ticket_medio_real'] = pd.to_numeric(df['ticket_medio'], errors='coerce').fillna(0) / 100
df['empresa'] = df['empresa'].str.upper()
df['unidade'] = df['unidade'].str.upper()

# Metas
metas_unidades = {
    "TOKYO": {"BARRA DO CORDA": 650, "CHAPADINHA": 550, "SANTA INÊS": 2200, "SÃO JOÃO DOS PATOS": 435, "SÃO JOSÉ DE RIBAMAR": 2000},
    "STARCHECK": {"BACABAL": 1640, "BALSAS": 1505, "CAXIAS": 560, "CODÓ": 380, "PINHEIRO": 900, "SÃO LUÍS": 3200},
    "LOG": {"AÇAILÂNDIA": 1100, "CAROLINA": 135, "PRESIDENTE DUTRA": 875, "SÃO LUÍS": 4240, "TIMON": 980},
    "VELOX": {"ESTREITO": 463, "GRAJAÚ": 500, "IMPERATRIZ": 3350, "PEDREIRAS": 600, "SÃO LUÍS": 1850}
}
metas_gerais = {"TOKYO": 5835, "STARCHECK": 8305, "LOG": 7330, "VELOX": 6763}

# Dias úteis
st.sidebar.header("📅 Dias úteis do mês")
dias_uteis_total = st.sidebar.number_input("Dias úteis no mês", 1, 31, 21)
dias_uteis_passados = st.sidebar.number_input("Dias úteis já passados", 0, 31, 16)
dias_uteis_restantes = max(dias_uteis_total - dias_uteis_passados, 1)

# Filtro de empresa
empresas = df['empresa'].unique()
empresa_selecionada = st.selectbox("Selecione a Marca:", empresas)
df_filtrado = df[df['empresa'] == empresa_selecionada]

# Consolidado da marca
meta_marca = metas_gerais.get(empresa_selecionada, 0)
realizado_marca = df_filtrado['total'].sum()
faltante_marca = meta_marca - realizado_marca
media_diaria = realizado_marca / dias_uteis_passados if dias_uteis_passados else 0
projecao_marca = media_diaria * dias_uteis_total
tendencia_marca = projecao_marca / meta_marca * 100 if meta_marca else 0
icone_tendencia = "🚀" if tendencia_marca >= 100 else "😟"
necessidade_dia_marca = faltante_marca / dias_uteis_restantes if dias_uteis_restantes else 0

# Cartões da marca
st.markdown("### 🏢 Consolidado - " + empresa_selecionada)
st.markdown(f"""
<style>
.card-container {{
  display: flex; gap: 20px; margin-bottom: 30px; flex-wrap: wrap;
}}
.card {{
  background-color: #f5f5f5; padding: 20px; border-radius: 12px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.1); text-align: center;
  min-width: 170px; flex: 1;
}}
.card h4 {{
  color: #cc3300; margin: 0 0 8px; font-size: 16px;
}}
.card h2 {{
  margin: 0; font-size: 26px; font-weight: bold; color: #222;
}}
</style>
<div class="card-container">
  <div class="card"><h4>Meta da Marca</h4><h2>{meta_marca}</h2></div>
  <div class="card"><h4>Realizado</h4><h2>{realizado_marca}</h2></div>
  <div class="card"><h4>Faltante</h4><h2>{faltante_marca}</h2></div>
  <div class="card"><h4>Necessidade/dia</h4><h2>{int(necessidade_dia_marca)}</h2></div>
  <div class="card"><h4>Projeção</h4><h2>{int(projecao_marca)}</h2></div>
  <div class="card"><h4>Tendência</h4><h2>{tendencia_marca:.0f}% {icone_tendencia}</h2></div>
</div>
""", unsafe_allow_html=True)

# Tabela por unidade
st.subheader("📍 Indicadores por Unidade")
dados = []
for _, row in df_filtrado.iterrows():
    unidade = row['unidade']
    realizado = row['total']
    meta = metas_unidades.get(empresa_selecionada, {}).get(unidade, 0)
    faltante = meta - realizado
    proj_dia = faltante / dias_uteis_restantes if dias_uteis_restantes else 0
    media = realizado / dias_uteis_passados if dias_uteis_passados else 0
    proj_final = media * dias_uteis_total
    tendencia = proj_final / meta * 100 if meta else 0
    icone_tend = "🚀" if tendencia >= 100 else "😟"
    ticket = round(row['ticket_medio_real'], 2)
    icone_ticket = "✅" if ticket >= 161.50 else "❌"
    pct_190 = row['%_190']
    icone_190 = "✅" if pct_190 >= 25 else "⚠️" if pct_190 >= 20 else "❌"

    dados.append({
        "Unidade": unidade,
        "Meta": meta,
        "Realizado": realizado,
        "Faltante": faltante,
        "Necessidade/dia": round(proj_dia, 1),
        "Tendência": f"{tendencia:.0f}% {icone_tend}",
        "Ticket Médio (R$)": f"R$ {ticket:.2f} {icone_ticket}",
        "% ≥ R$190": f"{pct_190}% {icone_190}"
    })
st.dataframe(pd.DataFrame(dados), use_container_width=True)

# Gráfico
st.subheader("📊 Produção Realizada por Unidade")
unidades = df_filtrado["unidade"]
producoes = df_filtrado["total"]

fig, ax = plt.subplots(figsize=(10, 5))
barras = ax.bar(unidades, producoes, color="royalblue")
for barra in barras:
    altura = barra.get_height()
    ax.annotate(f'{int(altura)}', xy=(barra.get_x() + barra.get_width()/2, altura),
                xytext=(0, 5), textcoords="offset points",
                ha='center', va='bottom', fontsize=10, fontweight='bold')
plt.xticks(rotation=0)
ax.set_ylabel("Produção")
ax.set_xlabel("Unidade")
ax.set_title("Produção Realizada por Unidade")
st.pyplot(fig)

# Consolidado Geral
st.markdown("---")
st.markdown("## 🏢 Consolidado Geral - Total das 4 Marcas")

meta_geral = sum(metas_gerais.values())
realizado_geral = df['total'].sum()
faltante_geral = meta_geral - realizado_geral
media_geral = realizado_geral / dias_uteis_passados if dias_uteis_passados else 0
projecao_geral = media_geral * dias_uteis_total
tendencia_geral = projecao_geral / meta_geral * 100 if meta_geral else 0
icone_geral = "🚀" if tendencia_geral >= 100 else "😟"
necessidade_dia_geral = faltante_geral / dias_uteis_restantes if dias_uteis_restantes else 0

st.markdown(f"""
<div class="card-container">
  <div class="card"><h4>Meta Geral</h4><h2>{meta_geral}</h2></div>
  <div class="card"><h4>Realizado</h4><h2>{realizado_geral}</h2></div>
  <div class="card"><h4>Faltante</h4><h2>{faltante_geral}</h2></div>
  <div class="card"><h4>Necessidade/dia</h4><h2>{int(necessidade_dia_geral)}</h2></div>
  <div class="card"><h4>Projeção</h4><h2>{int(projecao_geral)}</h2></div>
  <div class="card"><h4>Tendência</h4><h2>{tendencia_geral:.0f}% {icone_geral}</h2></div>
</div>
""", unsafe_allow_html=True)