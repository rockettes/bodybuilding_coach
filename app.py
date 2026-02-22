"""
app.py — Pro Coach IA | Sistema de Periodização e Autorregulação IFBB Pro
──────────────────────────────────────────────────────────────────────────────
Interface Streamlit com:
  - CRUD completo de registros diários
  - Timeline de periodização (histórico + projeção)
  - Módulo nutricional adaptativo com termogênese adaptativa
  - Prescrição diária por VFC + ACWR + CV-VFC
  - Plano semanal de treino (MEV/MAV/MRV + RIR + Técnicas)
  - Módulo de suplementação baseado em evidências
  - Painel de referências científicas (APA) colapsável
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import json
import os
from datetime import datetime, timedelta

from calculos_fisio import (
    AtletaMetrics,
    calcular_macros_semana,
    calcular_zonas_karvonen,
    sugerir_fase_e_timeline,
    gerar_treino_semanal,
    prescrever_treino_do_dia,
    calcular_acwr,
    calcular_cv_vfc,
    recomendar_suplementos,
)
from references import REFERENCIAS, get_refs_por_modulo


# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Pro Coach IA - Periodização IFBB",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🧬 Pro Coach IA — Periodização Científica IFBB Pro")
st.caption("Todas as recomendações são baseadas em literatura científica peer-reviewed.")


# ─────────────────────────────────────────────────────────────────────────────
# BANCO DE EXERCÍCIOS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def load_db():
    with open("banco_exercicios.json", "r", encoding="utf-8") as f:
        return json.load(f)

exercicios_db = load_db()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — REGISTROS DIÁRIOS
# ─────────────────────────────────────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)
ARQUIVO_REGISTROS = os.path.join(DATA_DIR, "registros_atleta.csv")
COLUNAS_CSV = [
    "Data", "Peso", "BF_Atual", "Carga_Treino", "VFC_Atual", "Sleep_Score",
    "Recovery_Time", "FC_Repouso", "Fase_Historica", "Estrategia_Dieta",
    "Calorias", "Carboidratos", "Proteinas", "Gorduras",
]


def carregar_registros() -> pd.DataFrame:
    if os.path.exists(ARQUIVO_REGISTROS):
        df = pd.read_csv(ARQUIVO_REGISTROS)
        for col in COLUNAS_CSV:
            if col not in df.columns:
                df[col] = "—" if col in ["Fase_Historica", "Estrategia_Dieta"] else 0.0
        return df
    return pd.DataFrame(columns=COLUNAS_CSV)


def salvar_registro(nova_linha_dict: dict) -> None:
    df = carregar_registros()
    nova_linha_df = pd.DataFrame([nova_linha_dict])
    df = pd.concat([df, nova_linha_df], ignore_index=True)
    df = df.drop_duplicates(subset=["Data"], keep="last").sort_values("Data")
    df.to_csv(ARQUIVO_REGISTROS, index=False)


def deletar_registro(data_str: str) -> None:
    df = carregar_registros()
    df = df[df["Data"] != data_str]
    df.to_csv(ARQUIVO_REGISTROS, index=False)


df_historico = carregar_registros()


# ─────────────────────────────────────────────────────────────────────────────
# TABELA CRUD INTERATIVA
# ─────────────────────────────────────────────────────────────────────────────

st.subheader("💾 Histórico Diário de Registros")
st.caption("Clique em uma linha para pré-carregar os dados na barra lateral (modo edição).")

event = st.dataframe(
    df_historico.sort_values(by="Data", ascending=False),
    on_select="rerun",
    selection_mode="single-row",
    use_container_width=True,
)

is_update_mode = False
if len(event.selection.rows) > 0:
    is_update_mode = True
    row_idx = event.selection.rows[0]
    row_data = df_historico.sort_values(by="Data", ascending=False).iloc[row_idx]
    def_data = datetime.strptime(row_data["Data"], "%Y-%m-%d").date()
    def_peso = float(row_data["Peso"])
    def_bf = float(row_data["BF_Atual"])
    def_carga = float(row_data["Carga_Treino"])
    def_vfc = float(row_data["VFC_Atual"])
    def_sleep = int(row_data["Sleep_Score"])
    def_rec = int(row_data["Recovery_Time"])
    def_fc = int(row_data["FC_Repouso"])
else:
    def_data = datetime.today().date()
    def_peso, def_bf, def_carga = 85.0, 12.0, 300.0
    def_vfc, def_sleep, def_rec, def_fc = 60.0, 75, 24, 55


# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — PERFIL E FORMULÁRIO DIÁRIO
# ─────────────────────────────────────────────────────────────────────────────

st.sidebar.header("👤 Perfil Base do Atleta")
sexo = st.sidebar.radio("Sexo Biológico", ["Masculino", "Feminino"])
categoria_alvo = st.sidebar.selectbox(
    "Categoria Alvo",
    ["Mens Physique", "Classic Physique", "Bodybuilding Open", "Bikini", "Wellness"],
)
idade = st.sidebar.number_input("Idade", value=28, step=1)
bf_alvo = st.sidebar.number_input("% BF Alvo (Palco)", value=5.0, step=0.1)
data_competicao = st.sidebar.date_input(
    "Data da Competição Alvo",
    value=datetime.today().date() + timedelta(days=120),
)
peds = st.sidebar.checkbox("Uso de PEDs?", value=True)
vfc_base = st.sidebar.number_input("VFC Média Baseline (últimos 7 dias)", value=65.0, step=1.0)
estagnado = st.sidebar.number_input("Dias de estagnação de peso", value=0, step=1)

st.sidebar.divider()
st.sidebar.header("📝 Registro Diário")

data_registro = st.sidebar.date_input("Data do Registro", value=def_data)
peso_atual = st.sidebar.number_input("Peso (kg)", value=def_peso, step=0.1)
bf_atual = st.sidebar.number_input("% BF Atual", value=def_bf, step=0.1)
carga_treino = st.sidebar.number_input("Volume Load do Treino (kg×reps)", value=def_carga, step=10.0)

st.sidebar.subheader("📡 Métricas Garmin")
vfc_atual = st.sidebar.number_input("VFC Noite Anterior (ms)", value=def_vfc, step=1.0)
sleep_score = st.sidebar.slider("Sleep Score", 0, 100, def_sleep)
recovery_time = st.sidebar.number_input("Recovery Time (horas)", value=def_rec, step=1)
fc_repouso = st.sidebar.number_input("FC Repouso (bpm)", value=def_fc, step=1)


# ─────────────────────────────────────────────────────────────────────────────
# LÓGICA CENTRAL — FASE + ATLETA + DIETA
# ─────────────────────────────────────────────────────────────────────────────

fase_sugerida, df_timeline, flags = sugerir_fase_e_timeline(
    datetime.today().date(), data_competicao, bf_atual, sexo, df_historico
)

atleta_atual = AtletaMetrics(
    categoria_alvo=categoria_alvo,
    peso=peso_atual,
    bf_atual=bf_atual,
    bf_alvo=bf_alvo,
    idade=idade,
    vfc_base=vfc_base,
    vfc_atual=vfc_atual,
    sleep_score=sleep_score,
    recovery_time=recovery_time,
    fc_repouso=fc_repouso,
    carga_treino=carga_treino,
    fase_sugerida=fase_sugerida,
    uso_peds=peds,
    estagnado_dias=estagnado,
    data_competicao=data_competicao,
)

df_dieta_semana, motivo_dieta, alertas_nutri = calcular_macros_semana(atleta_atual, df_historico, flags)
dia_semana_idx = data_registro.weekday()
dieta_hoje = df_dieta_semana.iloc[dia_semana_idx]

dados_input = {
    "Data": str(data_registro),
    "Peso": peso_atual,
    "BF_Atual": bf_atual,
    "Carga_Treino": carga_treino,
    "VFC_Atual": vfc_atual,
    "Sleep_Score": sleep_score,
    "Recovery_Time": recovery_time,
    "FC_Repouso": fc_repouso,
    "Fase_Historica": fase_sugerida,
    "Estrategia_Dieta": dieta_hoje["Estratégia"],
    "Calorias": dieta_hoje["Calorias"],
    "Carboidratos": dieta_hoje["Carb(g)"],
    "Proteinas": dieta_hoje["Prot(g)"],
    "Gorduras": dieta_hoje["Gord(g)"],
}

# Botões CRUD
if is_update_mode:
    col_up, col_del = st.sidebar.columns(2)
    if col_up.button("✏️ Atualizar", type="primary"):
        salvar_registro(dados_input)
        st.rerun()
    if col_del.button("🗑️ Deletar"):
        deletar_registro(str(data_registro))
        st.rerun()
else:
    if st.sidebar.button("💾 Salvar Registro do Dia", type="primary"):
        salvar_registro(dados_input)
        st.rerun()

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# SEÇÃO 1 — TIMELINE DE PERIODIZAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

st.header("🗓️ Timeline de Periodização")

col_fase1, col_fase2, col_fase3 = st.columns(3)
col_fase1.metric("Fase Atual", fase_sugerida)
dias_para_show = (data_competicao - datetime.today().date()).days
col_fase2.metric("Dias para o Show", f"{max(0, dias_para_show)}d")
taxa_str = f"{flags['taxa_perda_peso']:.2f}%/sem" if flags.get('taxa_perda_peso') is not None else "Dados insuficientes"
col_fase3.metric("Taxa de Perda de Peso", taxa_str)

# Alertas de fase
if flags.get("plato_metabolico"):
    st.error(
        "🚨 **PLATÔ METABÓLICO DETECTADO:** Taxa de perda < 0.5%/semana por 2 semanas. "
        "Protocolo de quebra de platô ativado. *(Peos et al., 2019)*"
    )

if not df_timeline.empty:
    fig_timeline = px.timeline(
        df_timeline,
        x_start="Inicio",
        x_end="Fim",
        y="Fase",
        color="Fase",
        color_discrete_sequence=px.colors.qualitative.Pastel,
    )
    fig_timeline.add_vline(
        x=datetime.today().strftime("%Y-%m-%d"),
        line_width=3,
        line_dash="dash",
        line_color="red",
    )
    fig_timeline.add_annotation(
        x=datetime.today().strftime("%Y-%m-%d"),
        y=1.05,
        yref="paper",
        text="HOJE",
        showarrow=False,
        font=dict(color="red", size=14),
        bgcolor="rgba(255,255,255,0.8)",
    )
    fig_timeline.update_yaxes(autorange="reversed")
    st.plotly_chart(fig_timeline, use_container_width=True)

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# SEÇÃO 2 — RECUPERAÇÃO + VFC + ACWR
# ─────────────────────────────────────────────────────────────────────────────

st.header("🎯 Status de Recuperação e Ação do Dia")

(status_dia, acao_dia, motivo_dia, painel_metricas,
 acwr_val, acwr_status, cv_vfc_val, cv_status) = prescrever_treino_do_dia(atleta_atual, df_historico)

st.caption(painel_metricas)

col_status, col_acwr, col_cv = st.columns(3)

with col_status:
    if "Severa" in status_dia:
        st.error(f"**{status_dia}**")
        st.error(f"**AÇÃO:** {acao_dia}")
    elif "Incompleta" in status_dia:
        st.warning(f"**{status_dia}**")
        st.warning(f"**AÇÃO:** {acao_dia}")
    else:
        st.success(f"**{status_dia}**")
        st.success(f"**AÇÃO:** {acao_dia}")

with col_acwr:
    st.subheader("⚖️ ACWR")
    if acwr_val is not None:
        # Gauge visual do ACWR
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=acwr_val,
            title={"text": "Acute:Chronic Workload Ratio"},
            gauge={
                "axis": {"range": [0, 2.5], "tickwidth": 1},
                "bar": {"color": "darkblue"},
                "steps": [
                    {"range": [0, 0.8], "color": "#4FC3F7"},
                    {"range": [0.8, 1.3], "color": "#81C784"},
                    {"range": [1.3, 1.5], "color": "#FFD54F"},
                    {"range": [1.5, 2.5], "color": "#E57373"},
                ],
                "threshold": {"line": {"color": "red", "width": 4}, "thickness": 0.75, "value": 1.5},
            },
        ))
        fig_gauge.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)
    st.caption(acwr_status)

with col_cv:
    st.subheader("📊 CV da VFC (7d)")
    if cv_vfc_val is not None:
        color = "#E57373" if cv_vfc_val > 10 else ("#FFD54F" if cv_vfc_val > 7 else "#81C784")
        st.markdown(
            f"<h1 style='text-align:center; color:{color}'>{cv_vfc_val}%</h1>",
            unsafe_allow_html=True,
        )
    st.caption(cv_status)

with st.expander("📖 Base Científica — Recuperação e VFC"):
    for ref in get_refs_por_modulo("Recuperação"):
        st.markdown(
            f"<span style='background:{ref['badge_color']};color:white;padding:2px 8px;"
            f"border-radius:8px;font-size:0.8em'>{ref['modulo']}</span> {ref['apa']}<br>"
            f"<i style='color:gray;font-size:0.85em'>{ref['resumo']}</i><br><br>",
            unsafe_allow_html=True,
        )

st.info(f"**POR QUÊ?** {motivo_dia}")

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# SEÇÃO 3 — NUTRIÇÃO ADAPTATIVA
# ─────────────────────────────────────────────────────────────────────────────

col_nutri, col_cardio = st.columns([2, 1])

with col_nutri:
    st.subheader(f"🍽️ Plano Nutricional Semanal — {fase_sugerida}")

    # Alertas nutricionais adaptativos
    for key, msg in alertas_nutri.items():
        if key == "get_base":
            st.caption(f"⚙️ {msg}")
        elif "⚠️" in msg or "🔴" in msg:
            st.warning(msg)

    st.markdown(motivo_dieta)
    st.write(
        f"**Alvo de HOJE ({dieta_hoje['Dia']}):** "
        f"{dieta_hoje['Estratégia']} → **{dieta_hoje['Calorias']} kcal** | "
        f"C: {dieta_hoje['Carb(g)']}g | P: {dieta_hoje['Prot(g)']}g | G: {dieta_hoje['Gord(g)']}g"
    )
    st.dataframe(df_dieta_semana, use_container_width=True, hide_index=True)

    with st.expander("📖 Base Científica — Nutrição"):
        for ref in get_refs_por_modulo("Nutrição"):
            st.markdown(
                f"<span style='background:{ref['badge_color']};color:white;padding:2px 8px;"
                f"border-radius:8px;font-size:0.8em'>{ref['modulo']}</span> {ref['apa']}<br>"
                f"<i style='color:gray;font-size:0.85em'>{ref['resumo']}</i><br><br>",
                unsafe_allow_html=True,
            )

with col_cardio:
    st.subheader("🏃‍♂️ Zonas de FC (Karvonen)")
    zonas = calcular_zonas_karvonen(idade, fc_repouso)
    zona_labels = {
        "Zona 1 (Recuperação Ativa)": "🔵",
        "Zona 2 (LISS / Fat-Burning)": "🟢",
        "Zona 3 (Aeróbio Moderado)": "🟡",
        "Zona 4 (Limiar Anaeróbio)": "🟠",
        "Zona 5 (HIIT / Máximo)": "🔴",
    }
    for zona, (min_fc, max_fc) in zonas.items():
        emoji = zona_labels.get(zona, "")
        st.write(f"{emoji} **{zona}:** {min_fc}–{max_fc} bpm")

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# SEÇÃO 4 — TREINO SEMANAL
# ─────────────────────────────────────────────────────────────────────────────

st.header("🏋️‍♂️ Plano de Treino Semanal")
df_treino, motivo_treino = gerar_treino_semanal(atleta_atual, exercicios_db)
st.markdown(motivo_treino)
st.dataframe(df_treino, use_container_width=True, hide_index=True)

csv_treino = df_treino.to_csv(sep=";", index=False)
st.download_button(
    label="📥 Baixar Planilha de Treino (CSV)",
    data=csv_treino,
    file_name=f"treino_{fase_sugerida.lower().replace(' ', '_')}.csv",
    mime="text/csv",
)

with st.expander("📖 Base Científica — Treino"):
    for ref in get_refs_por_modulo("Treino"):
        st.markdown(
            f"<span style='background:{ref['badge_color']};color:white;padding:2px 8px;"
            f"border-radius:8px;font-size:0.8em'>{ref['modulo']}</span> {ref['apa']}<br>"
            f"<i style='color:gray;font-size:0.85em'>{ref['resumo']}</i><br><br>",
            unsafe_allow_html=True,
        )

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# SEÇÃO 5 — SUPLEMENTAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

st.header("💊 Suplementação Baseada em Evidências")
st.caption("Apenas suplementos com evidência Grau A ou B incluídos.")
df_supl = recomendar_suplementos(atleta_atual)
st.dataframe(df_supl, use_container_width=True, hide_index=True)

with st.expander("📖 Base Científica — Suplementação"):
    for ref in get_refs_por_modulo("Suplementação"):
        st.markdown(
            f"<span style='background:{ref['badge_color']};color:white;padding:2px 8px;"
            f"border-radius:8px;font-size:0.8em'>{ref['modulo']}</span> {ref['apa']}<br>"
            f"<i style='color:gray;font-size:0.85em'>{ref['resumo']}</i><br><br>",
            unsafe_allow_html=True,
        )

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# SEÇÃO 6 — GRÁFICOS DE EVOLUÇÃO
# ─────────────────────────────────────────────────────────────────────────────

st.header("📈 Análise de Evolução")

if not df_historico.empty and len(df_historico) >= 2:
    df_plot = df_historico.sort_values(by="Data")

    # Gráfico VFC vs Carga
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_plot["Data"], y=df_plot["VFC_Atual"].astype(float),
        mode="lines+markers", name="VFC (ms)", yaxis="y1",
        line=dict(color="#00e676", width=2), marker=dict(size=6),
    ))
    fig.add_trace(go.Bar(
        x=df_plot["Data"], y=df_plot["Carga_Treino"].astype(float),
        name="Volume Load", yaxis="y2", opacity=0.4,
        marker_color="#EF5350",
    ))
    fig.update_layout(
        title="VFC vs Volume de Treino (Correlação SNC)",
        yaxis=dict(
            title=dict(text="VFC (ms)", font=dict(color="#00e676")),
            tickfont=dict(color="#00e676"),
        ),
        yaxis2=dict(
            title=dict(text="Volume Load", font=dict(color="#EF5350")),
            tickfont=dict(color="#EF5350"),
            overlaying="y",
            side="right",
        ),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Gráfico Peso + BF
    if "BF_Atual" in df_plot.columns:
        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(
            x=df_plot["Data"], y=df_plot["Peso"].astype(float),
            mode="lines+markers", name="Peso (kg)", yaxis="y1",
            line=dict(color="#42A5F5", width=2),
        ))
        fig2.add_trace(go.Scatter(
            x=df_plot["Data"], y=df_plot["BF_Atual"].astype(float),
            mode="lines+markers", name="BF %", yaxis="y2",
            line=dict(color="#FFA726", width=2, dash="dash"),
        ))
        fig2.update_layout(
            title="Evolução de Peso e % BF",
            yaxis=dict(
                title=dict(text="Peso (kg)", font=dict(color="#42A5F5")),
                tickfont=dict(color="#42A5F5"),
            ),
            yaxis2=dict(
                title=dict(text="BF %", font=dict(color="#FFA726")),
                tickfont=dict(color="#FFA726"),
                overlaying="y",
                side="right",
            ),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
        )
        st.plotly_chart(fig2, use_container_width=True)
else:
    st.info("📊 Registre pelo menos 2 dias de dados para visualizar os gráficos de evolução.")

st.divider()


# ─────────────────────────────────────────────────────────────────────────────
# SEÇÃO 7 — PAINEL COMPLETO DE REFERÊNCIAS CIENTÍFICAS
# ─────────────────────────────────────────────────────────────────────────────

st.header("📚 Base Científica Completa do Plano")
st.caption("Todas as referências utilizadas nas recomendações deste sistema, formatadas em APA.")

modulos = ["Periodização", "Nutrição", "Treino", "Recuperação", "Suplementação"]
cores_modulo = {
    "Periodização": "#6C63FF",
    "Nutrição": "#FF6B6B",
    "Treino": "#4ECDC4",
    "Recuperação": "#FFD166",
    "Suplementação": "#A8DADC",
}

tabs = st.tabs([f"{'🟣' if m=='Periodização' else '🔴' if m=='Nutrição' else '🟢' if m=='Treino' else '🟡' if m=='Recuperação' else '🔵'} {m}" for m in modulos])

for i, modulo in enumerate(modulos):
    with tabs[i]:
        refs_modulo = get_refs_por_modulo(modulo)
        for ref in refs_modulo:
            cor = cores_modulo.get(modulo, "#888")
            st.markdown(
                f"<div style='border-left: 4px solid {cor}; padding: 8px 12px; margin-bottom: 12px; "
                f"background: rgba(0,0,0,0.03); border-radius: 4px;'>"
                f"<b style='font-size:0.9em'>{ref['apa']}</b><br>"
                f"<i style='color:#555;font-size:0.85em'>💡 {ref['resumo']}</i>"
                f"</div>",
                unsafe_allow_html=True,
            )

st.divider()
st.caption(
    "⚕️ **Aviso Legal:** Este sistema é uma ferramenta de suporte educacional e de planejamento. "
    "Não substitui a avaliação de profissionais de educação física, nutrição e medicina. "
    "Consulte sempre um especialista certificado."
)