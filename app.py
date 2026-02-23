"""
app.py — Pro Coach IA | Sistema de Periodização e Autorregulação IFBB Pro
──────────────────────────────────────────────────────────────────────────────
Interface Streamlit com:
  - Autenticação via Supabase (cadastro, login, logout)
  - Dados isolados por usuário via Row Level Security (RLS)
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
from supabase import create_client, Client

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


# ─────────────────────────────────────────────────────────────────────────────
# CLIENTE SUPABASE
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)

supabase = get_supabase()


# ─────────────────────────────────────────────────────────────────────────────
# BANCO DE EXERCÍCIOS
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_data
def load_db():
    with open("banco_exercicios.json", "r", encoding="utf-8") as f:
        return json.load(f)

exercicios_db = load_db()


# ─────────────────────────────────────────────────────────────────────────────
# AUTENTICAÇÃO — FUNÇÕES
# ─────────────────────────────────────────────────────────────────────────────

def fazer_login(email: str, senha: str) -> bool:
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": senha})
        st.session_state["session"] = res.session
        st.session_state["user"] = res.user
        return True
    except Exception as e:
        st.error(f"❌ Erro ao fazer login: {e}")
        return False


def fazer_cadastro(email: str, senha: str) -> bool:
    try:
        res = supabase.auth.sign_up({"email": email, "password": senha})
        if res.user:
            st.success("✅ Conta criada! Verifique seu e-mail para confirmar o cadastro e depois faça login.")
            return True
        return False
    except Exception as e:
        st.error(f"❌ Erro ao criar conta: {e}")
        return False


def fazer_logout():
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()


def get_user_id() -> str:
    return st.session_state["user"].id


def get_access_token() -> str:
    return st.session_state["session"].access_token


def sessao_ativa() -> bool:
    return "session" in st.session_state and st.session_state["session"] is not None


# ─────────────────────────────────────────────────────────────────────────────
# TELA DE LOGIN / CADASTRO
# ─────────────────────────────────────────────────────────────────────────────

def render_tela_auth():
    st.title("🧬 Pro Coach IA — Periodização Científica IFBB Pro")
    st.caption("Todas as recomendações são baseadas em literatura científica peer-reviewed.")
    st.divider()

    col_esq, col_dir = st.columns([1, 1], gap="large")

    with col_esq:
        st.subheader("🔐 Entrar na sua conta")
        with st.form("form_login"):
            email_login = st.text_input("E-mail", placeholder="seu@email.com")
            senha_login = st.text_input("Senha", type="password", placeholder="••••••••")
            btn_login = st.form_submit_button("Entrar", type="primary", use_container_width=True)

        if btn_login:
            if email_login and senha_login:
                if fazer_login(email_login, senha_login):
                    st.rerun()
            else:
                st.warning("Preencha e-mail e senha.")

    with col_dir:
        st.subheader("📝 Criar conta gratuita")
        with st.form("form_cadastro"):
            email_cad = st.text_input("E-mail", placeholder="seu@email.com", key="email_cad")
            senha_cad = st.text_input("Senha", type="password", placeholder="Mínimo 6 caracteres", key="senha_cad")
            senha_cad2 = st.text_input("Confirmar senha", type="password", placeholder="Repita a senha", key="senha_cad2")
            btn_cad = st.form_submit_button("Criar conta", use_container_width=True)

        if btn_cad:
            if not email_cad or not senha_cad:
                st.warning("Preencha todos os campos.")
            elif senha_cad != senha_cad2:
                st.error("❌ As senhas não coincidem.")
            elif len(senha_cad) < 6:
                st.error("❌ A senha precisa ter pelo menos 6 caracteres.")
            else:
                fazer_cadastro(email_cad, senha_cad)

    st.divider()
    st.caption("⚕️ Este sistema é uma ferramenta de suporte educacional. Não substitui avaliação profissional.")


# ─────────────────────────────────────────────────────────────────────────────
# CRUD SUPABASE — REGISTROS DO USUÁRIO LOGADO
# ─────────────────────────────────────────────────────────────────────────────

COLUNAS_SUPABASE = [
    "data", "peso", "bf_atual", "carga_treino", "vfc_atual", "sleep_score",
    "recovery_time", "fc_repouso", "fase_historica", "estrategia_dieta",
    "calorias", "carboidratos", "proteinas", "gorduras",
]

# snake_case (Supabase) → PascalCase (código interno)
RENAME_MAP = {
    "data": "Data", "peso": "Peso", "bf_atual": "BF_Atual",
    "carga_treino": "Carga_Treino", "vfc_atual": "VFC_Atual",
    "sleep_score": "Sleep_Score", "recovery_time": "Recovery_Time",
    "fc_repouso": "FC_Repouso", "fase_historica": "Fase_Historica",
    "estrategia_dieta": "Estrategia_Dieta", "calorias": "Calorias",
    "carboidratos": "Carboidratos", "proteinas": "Proteinas", "gorduras": "Gorduras",
}


def carregar_registros() -> pd.DataFrame:
    """Carrega apenas os registros do usuário logado (RLS garante isolamento)."""
    try:
        token = get_access_token()
        res = (
            supabase.postgrest
            .auth(token)
            .from_("registros_atleta")
            .select(",".join(COLUNAS_SUPABASE))
            .order("data", desc=False)
            .execute()
        )
        if res.data:
            df = pd.DataFrame(res.data)
            return df.rename(columns=RENAME_MAP)
        return pd.DataFrame(columns=list(RENAME_MAP.values()))
    except Exception as e:
        st.error(f"Erro ao carregar registros: {e}")
        return pd.DataFrame(columns=list(RENAME_MAP.values()))


def salvar_registro(dados: dict) -> None:
    """Upsert: insere ou atualiza registro do dia para o usuário logado."""
    try:
        token = get_access_token()
        payload = {
            "user_id":          get_user_id(),
            "data":             dados["Data"],
            "peso":             dados["Peso"],
            "bf_atual":         dados["BF_Atual"],
            "carga_treino":     dados["Carga_Treino"],
            "vfc_atual":        dados["VFC_Atual"],
            "sleep_score":      dados["Sleep_Score"],
            "recovery_time":    dados["Recovery_Time"],
            "fc_repouso":       dados["FC_Repouso"],
            "fase_historica":   dados["Fase_Historica"],
            "estrategia_dieta": dados["Estrategia_Dieta"],
            "calorias":         dados["Calorias"],
            "carboidratos":     dados["Carboidratos"],
            "proteinas":        dados["Proteinas"],
            "gorduras":         dados["Gorduras"],
        }
        (
            supabase.postgrest
            .auth(token)
            .from_("registros_atleta")
            .upsert(payload, on_conflict="user_id,data")
            .execute()
        )
    except Exception as e:
        st.error(f"Erro ao salvar registro: {e}")


def deletar_registro(data_str: str) -> None:
    """Deleta o registro do dia do usuário logado."""
    try:
        token = get_access_token()
        (
            supabase.postgrest
            .auth(token)
            .from_("registros_atleta")
            .delete()
            .eq("user_id", get_user_id())
            .eq("data", data_str)
            .execute()
        )
    except Exception as e:
        st.error(f"Erro ao deletar registro: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# APP PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def render_app():

    # Cabeçalho + logout
    col_titulo, col_user = st.columns([4, 1])
    with col_titulo:
        st.title("🧬 Pro Coach IA — Periodização Científica IFBB Pro")
        st.caption("Todas as recomendações são baseadas em literatura científica peer-reviewed.")
    with col_user:
        st.caption(f"👤 {st.session_state['user'].email}")
        if st.button("Sair", use_container_width=True):
            fazer_logout()

    # ── Carregar dados do usuário ─────────────────────────────────────────────
    df_historico = carregar_registros()

    # ─────────────────────────────────────────────────────────────────────────
    # TABELA CRUD
    # ─────────────────────────────────────────────────────────────────────────

    st.subheader("💾 Histórico Diário de Registros")
    st.caption("Clique em uma linha para pré-carregar os dados na barra lateral (modo edição).")

    df_display = df_historico.sort_values(by="Data", ascending=False) if not df_historico.empty else df_historico
    event = st.dataframe(df_display, on_select="rerun", selection_mode="single-row", use_container_width=True)

    is_update_mode = False
    if not df_historico.empty and len(event.selection.rows) > 0:
        is_update_mode = True
        row_data = df_display.iloc[event.selection.rows[0]]
        def_data  = datetime.strptime(str(row_data["Data"]), "%Y-%m-%d").date()
        def_peso  = float(row_data["Peso"])
        def_bf    = float(row_data["BF_Atual"])
        def_carga = float(row_data["Carga_Treino"])
        def_vfc   = float(row_data["VFC_Atual"])
        def_sleep = int(row_data["Sleep_Score"])
        def_rec   = int(row_data["Recovery_Time"])
        def_fc    = int(row_data["FC_Repouso"])
    else:
        def_data  = datetime.today().date()
        def_peso, def_bf, def_carga       = 85.0, 12.0, 300.0
        def_vfc, def_sleep, def_rec, def_fc = 60.0, 75, 24, 55

    # ─────────────────────────────────────────────────────────────────────────
    # SIDEBAR
    # ─────────────────────────────────────────────────────────────────────────

    st.sidebar.header("👤 Perfil Base do Atleta")
    sexo           = st.sidebar.radio("Sexo Biológico", ["Masculino", "Feminino"])
    categoria_alvo = st.sidebar.selectbox("Categoria Alvo",
        ["Mens Physique", "Classic Physique", "Bodybuilding Open", "Bikini", "Wellness"])
    idade          = st.sidebar.number_input("Idade", value=28, step=1)
    bf_alvo        = st.sidebar.number_input("% BF Alvo (Palco)", value=5.0, step=0.1)
    data_competicao = st.sidebar.date_input("Data da Competição Alvo",
        value=datetime.today().date() + timedelta(days=120))
    peds           = st.sidebar.checkbox("Uso de PEDs?", value=True)
    vfc_base       = st.sidebar.number_input("VFC Média Baseline (últimos 7 dias)", value=65.0, step=1.0)
    estagnado      = st.sidebar.number_input("Dias de estagnação de peso", value=0, step=1)

    st.sidebar.divider()
    st.sidebar.header("📝 Registro Diário")

    data_registro = st.sidebar.date_input("Data do Registro", value=def_data)
    peso_atual    = st.sidebar.number_input("Peso (kg)", value=def_peso, step=0.1)
    bf_atual      = st.sidebar.number_input("% BF Atual", value=def_bf, step=0.1)
    carga_treino  = st.sidebar.number_input("Volume Load do Treino (kg×reps)", value=def_carga, step=10.0)

    st.sidebar.subheader("📡 Métricas Garmin")
    vfc_atual     = st.sidebar.number_input("VFC Noite Anterior (ms)", value=def_vfc, step=1.0)
    sleep_score   = st.sidebar.slider("Sleep Score", 0, 100, def_sleep)
    recovery_time = st.sidebar.number_input("Recovery Time (horas)", value=def_rec, step=1)
    fc_repouso    = st.sidebar.number_input("FC Repouso (bpm)", value=def_fc, step=1)

    # ─────────────────────────────────────────────────────────────────────────
    # LÓGICA CENTRAL
    # ─────────────────────────────────────────────────────────────────────────

    fase_sugerida, df_timeline, flags = sugerir_fase_e_timeline(
        datetime.today().date(), data_competicao, bf_atual, sexo, df_historico
    )

    atleta_atual = AtletaMetrics(
        categoria_alvo=categoria_alvo, peso=peso_atual, bf_atual=bf_atual,
        bf_alvo=bf_alvo, idade=idade, vfc_base=vfc_base, vfc_atual=vfc_atual,
        sleep_score=sleep_score, recovery_time=recovery_time, fc_repouso=fc_repouso,
        carga_treino=carga_treino, fase_sugerida=fase_sugerida, uso_peds=peds,
        estagnado_dias=estagnado, data_competicao=data_competicao,
    )

    df_dieta_semana, motivo_dieta, alertas_nutri = calcular_macros_semana(atleta_atual, df_historico, flags)
    dieta_hoje = df_dieta_semana.iloc[data_registro.weekday()]

    dados_input = {
        "Data": str(data_registro), "Peso": peso_atual, "BF_Atual": bf_atual,
        "Carga_Treino": carga_treino, "VFC_Atual": vfc_atual, "Sleep_Score": sleep_score,
        "Recovery_Time": recovery_time, "FC_Repouso": fc_repouso,
        "Fase_Historica": fase_sugerida, "Estrategia_Dieta": dieta_hoje["Estratégia"],
        "Calorias": dieta_hoje["Calorias"], "Carboidratos": dieta_hoje["Carb(g)"],
        "Proteinas": dieta_hoje["Prot(g)"], "Gorduras": dieta_hoje["Gord(g)"],
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

    # ─────────────────────────────────────────────────────────────────────────
    # SEÇÃO 1 — TIMELINE
    # ─────────────────────────────────────────────────────────────────────────

    st.header("🗓️ Timeline de Periodização")
    c1, c2, c3 = st.columns(3)
    c1.metric("Fase Atual", fase_sugerida)
    c2.metric("Dias para o Show", f"{max(0,(data_competicao - datetime.today().date()).days)}d")
    taxa_str = f"{flags['taxa_perda_peso']:.2f}%/sem" if flags.get("taxa_perda_peso") else "Dados insuficientes"
    c3.metric("Taxa de Perda de Peso", taxa_str)

    if flags.get("plato_metabolico"):
        st.error("🚨 **PLATÔ METABÓLICO DETECTADO:** Taxa < 0.5%/sem por 2 semanas. Protocolo de quebra ativado. *(Peos et al., 2019)*")

    if not df_timeline.empty:
        fig_t = px.timeline(df_timeline, x_start="Inicio", x_end="Fim", y="Fase",
            color="Fase", color_discrete_sequence=px.colors.qualitative.Pastel)
        fig_t.add_vline(x=datetime.today().strftime("%Y-%m-%d"), line_width=3, line_dash="dash", line_color="red")
        fig_t.add_annotation(x=datetime.today().strftime("%Y-%m-%d"), y=1.05, yref="paper",
            text="HOJE", showarrow=False, font=dict(color="red", size=14), bgcolor="rgba(255,255,255,0.8)")
        fig_t.update_yaxes(autorange="reversed")
        st.plotly_chart(fig_t, use_container_width=True)

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # SEÇÃO 2 — RECUPERAÇÃO
    # ─────────────────────────────────────────────────────────────────────────

    st.header("🎯 Status de Recuperação e Ação do Dia")
    (status_dia, acao_dia, motivo_dia, painel_metricas,
     acwr_val, acwr_status, cv_vfc_val, cv_status) = prescrever_treino_do_dia(atleta_atual, df_historico)

    st.caption(painel_metricas)
    col_s, col_a, col_c = st.columns(3)

    with col_s:
        fn = st.error if "Severa" in status_dia else (st.warning if "Incompleta" in status_dia else st.success)
        fn(f"**{status_dia}**")
        fn(f"**AÇÃO:** {acao_dia}")

    with col_a:
        st.subheader("⚖️ ACWR")
        if acwr_val is not None:
            fig_g = go.Figure(go.Indicator(
                mode="gauge+number", value=acwr_val,
                title={"text": "Acute:Chronic Workload Ratio"},
                gauge={"axis": {"range": [0, 2.5]}, "bar": {"color": "darkblue"},
                    "steps": [{"range": [0, 0.8], "color": "#4FC3F7"},
                               {"range": [0.8, 1.3], "color": "#81C784"},
                               {"range": [1.3, 1.5], "color": "#FFD54F"},
                               {"range": [1.5, 2.5], "color": "#E57373"}],
                    "threshold": {"line": {"color": "red", "width": 4}, "thickness": 0.75, "value": 1.5}},
            ))
            fig_g.update_layout(height=200, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig_g, use_container_width=True)
        st.caption(acwr_status)

    with col_c:
        st.subheader("📊 CV da VFC (7d)")
        if cv_vfc_val is not None:
            cor = "#E57373" if cv_vfc_val > 10 else ("#FFD54F" if cv_vfc_val > 7 else "#81C784")
            st.markdown(f"<h1 style='text-align:center;color:{cor}'>{cv_vfc_val}%</h1>", unsafe_allow_html=True)
        st.caption(cv_status)

    with st.expander("📖 Base Científica — Recuperação e VFC"):
        _render_refs("Recuperação")

    st.info(f"**POR QUÊ?** {motivo_dia}")
    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # SEÇÃO 3 — NUTRIÇÃO
    # ─────────────────────────────────────────────────────────────────────────

    col_n, col_card = st.columns([2, 1])
    with col_n:
        st.subheader(f"🍽️ Plano Nutricional Semanal — {fase_sugerida}")
        for key, msg in alertas_nutri.items():
            if key == "get_base":
                st.caption(f"⚙️ {msg}")
            elif "⚠️" in msg or "🔴" in msg:
                st.warning(msg)
        st.markdown(motivo_dieta)
        st.write(
            f"**Alvo de HOJE ({dieta_hoje['Dia']}):** {dieta_hoje['Estratégia']} → "
            f"**{dieta_hoje['Calorias']} kcal** | C: {dieta_hoje['Carb(g)']}g | "
            f"P: {dieta_hoje['Prot(g)']}g | G: {dieta_hoje['Gord(g)']}g"
        )
        st.dataframe(df_dieta_semana, use_container_width=True, hide_index=True)
        with st.expander("📖 Base Científica — Nutrição"):
            _render_refs("Nutrição")

    with col_card:
        st.subheader("🏃‍♂️ Zonas de FC (Karvonen)")
        zonas = calcular_zonas_karvonen(idade, fc_repouso)
        emojis_zona = {"Zona 1 (Recuperação Ativa)": "🔵", "Zona 2 (LISS / Fat-Burning)": "🟢",
                       "Zona 3 (Aeróbio Moderado)": "🟡", "Zona 4 (Limiar Anaeróbio)": "🟠", "Zona 5 (HIIT / Máximo)": "🔴"}
        for zona, (mn, mx) in zonas.items():
            st.write(f"{emojis_zona.get(zona,'')} **{zona}:** {mn}–{mx} bpm")

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # SEÇÃO 4 — TREINO
    # ─────────────────────────────────────────────────────────────────────────

    st.header("🏋️‍♂️ Plano de Treino Semanal")
    df_treino, motivo_treino = gerar_treino_semanal(atleta_atual, exercicios_db)
    st.markdown(motivo_treino)
    st.dataframe(df_treino, use_container_width=True, hide_index=True)
    st.download_button("📥 Baixar Planilha de Treino (CSV)",
        data=df_treino.to_csv(sep=";", index=False),
        file_name=f"treino_{fase_sugerida.lower().replace(' ','_')}.csv", mime="text/csv")
    with st.expander("📖 Base Científica — Treino"):
        _render_refs("Treino")

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # SEÇÃO 5 — SUPLEMENTAÇÃO
    # ─────────────────────────────────────────────────────────────────────────

    st.header("💊 Suplementação Baseada em Evidências")
    st.caption("Apenas suplementos com evidência Grau A ou B incluídos.")
    st.dataframe(recomendar_suplementos(atleta_atual), use_container_width=True, hide_index=True)
    with st.expander("📖 Base Científica — Suplementação"):
        _render_refs("Suplementação")

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # SEÇÃO 6 — GRÁFICOS
    # ─────────────────────────────────────────────────────────────────────────

    st.header("📈 Análise de Evolução")

    if not df_historico.empty and len(df_historico) >= 2:
        df_plot = df_historico.sort_values("Data")

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_plot["Data"], y=df_plot["VFC_Atual"].astype(float),
            mode="lines+markers", name="VFC (ms)", yaxis="y1",
            line=dict(color="#00e676", width=2), marker=dict(size=6)))
        fig.add_trace(go.Bar(x=df_plot["Data"], y=df_plot["Carga_Treino"].astype(float),
            name="Volume Load", yaxis="y2", opacity=0.4, marker_color="#EF5350"))
        fig.update_layout(
            title="VFC vs Volume de Treino (Correlação SNC)",
            yaxis=dict(title=dict(text="VFC (ms)", font=dict(color="#00e676")), tickfont=dict(color="#00e676")),
            yaxis2=dict(title=dict(text="Volume Load", font=dict(color="#EF5350")),
                tickfont=dict(color="#EF5350"), overlaying="y", side="right"),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        st.plotly_chart(fig, use_container_width=True)

        fig2 = go.Figure()
        fig2.add_trace(go.Scatter(x=df_plot["Data"], y=df_plot["Peso"].astype(float),
            mode="lines+markers", name="Peso (kg)", yaxis="y1", line=dict(color="#42A5F5", width=2)))
        fig2.add_trace(go.Scatter(x=df_plot["Data"], y=df_plot["BF_Atual"].astype(float),
            mode="lines+markers", name="BF %", yaxis="y2", line=dict(color="#FFA726", width=2, dash="dash")))
        fig2.update_layout(
            title="Evolução de Peso e % BF",
            yaxis=dict(title=dict(text="Peso (kg)", font=dict(color="#42A5F5")), tickfont=dict(color="#42A5F5")),
            yaxis2=dict(title=dict(text="BF %", font=dict(color="#FFA726")),
                tickfont=dict(color="#FFA726"), overlaying="y", side="right"),
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)", hovermode="x unified",
        )
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("📊 Registre pelo menos 2 dias de dados para visualizar os gráficos de evolução.")

    st.divider()

    # ─────────────────────────────────────────────────────────────────────────
    # SEÇÃO 7 — REFERÊNCIAS COMPLETAS
    # ─────────────────────────────────────────────────────────────────────────

    st.header("📚 Base Científica Completa do Plano")
    st.caption("Todas as referências utilizadas nas recomendações deste sistema, formatadas em APA.")

    modulos  = ["Periodização", "Nutrição", "Treino", "Recuperação", "Suplementação"]
    emojis_m = {"Periodização": "🟣", "Nutrição": "🔴", "Treino": "🟢", "Recuperação": "🟡", "Suplementação": "🔵"}
    cores_m  = {"Periodização": "#6C63FF", "Nutrição": "#FF6B6B", "Treino": "#4ECDC4",
                "Recuperação": "#FFD166", "Suplementação": "#A8DADC"}

    for i, modulo in enumerate(st.tabs([f"{emojis_m[m]} {m}" for m in modulos])):
        with modulo:
            _render_refs(modulos[i], cores_m[modulos[i]], card=True)

    st.divider()
    st.caption("⚕️ **Aviso Legal:** Este sistema é uma ferramenta de suporte educacional e de planejamento. "
               "Não substitui a avaliação de profissionais de educação física, nutrição e medicina.")


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — renderizar referências
# ─────────────────────────────────────────────────────────────────────────────

def _render_refs(modulo: str, cor: str = None, card: bool = False):
    cores_m = {"Periodização": "#6C63FF", "Nutrição": "#FF6B6B", "Treino": "#4ECDC4",
               "Recuperação": "#FFD166", "Suplementação": "#A8DADC"}
    cor = cor or cores_m.get(modulo, "#888")
    for ref in get_refs_por_modulo(modulo):
        if card:
            st.markdown(
                f"<div style='border-left:4px solid {cor};padding:8px 12px;"
                f"margin-bottom:12px;background:rgba(0,0,0,0.03);border-radius:4px;'>"
                f"<b style='font-size:0.9em'>{ref['apa']}</b><br>"
                f"<i style='color:#555;font-size:0.85em'>💡 {ref['resumo']}</i></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<span style='background:{ref['badge_color']};color:white;padding:2px 8px;"
                f"border-radius:8px;font-size:0.8em'>{ref['modulo']}</span> {ref['apa']}<br>"
                f"<i style='color:gray;font-size:0.85em'>{ref['resumo']}</i><br><br>",
                unsafe_allow_html=True,
            )


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if not sessao_ativa():
    render_tela_auth()
else:
    render_app()