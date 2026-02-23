"""
app.py — Pro Coach IA | Sistema de Periodização e Autorregulação IFBB Pro
──────────────────────────────────────────────────────────────────────────────
v3.0 — Perfil persistido no Supabase, sidebar só para registro diário,
        navegação por abas, onboarding no primeiro acesso, idade calculada
        automaticamente a partir da data de nascimento.
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import numpy as np
import json
from datetime import datetime, date, timedelta
from supabase import create_client, Client

from calculos_fisio import (
    AtletaMetrics,
    calcular_macros_semana,
    calcular_zonas_karvonen,
    zonas_fc_manuais,
    sugerir_fase_e_timeline,
    gerar_treino_semanal,
    prescrever_treino_do_dia,
    calcular_acwr,
    calcular_cv_vfc,
    recomendar_suplementos,
    calcular_metas_semana,
    avaliar_resultados_semana,
    avaliar_proporcoes,
    calcular_bf_jackson_pollock7,
    calcular_bf_por_formula,
    sugerir_formula_dobras,
    FORMULAS_DOBRAS,
    PROPORCOES_CATEGORIA,
    PHI,
)
from references import get_refs_por_modulo

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURAÇÃO DA PÁGINA
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Pro Coach IA",
    page_icon="🧬",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# SUPABASE
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource
def get_supabase() -> Client:
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_ANON_KEY"])

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
# AUTENTICAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

def fazer_login(email: str, senha: str) -> bool:
    try:
        res = supabase.auth.sign_in_with_password({"email": email, "password": senha})
        st.session_state["session"] = res.session
        st.session_state["user"]    = res.user
        return True
    except Exception as e:
        st.error(f"❌ {e}")
        return False

def fazer_cadastro(email: str, senha: str) -> bool:
    try:
        res = supabase.auth.sign_up({"email": email, "password": senha})
        if res.user:
            st.success("✅ Conta criada! Faça login para continuar.")
            return True
        return False
    except Exception as e:
        st.error(f"❌ {e}")
        return False

def fazer_logout():
    supabase.auth.sign_out()
    st.session_state.clear()
    st.rerun()

def get_uid() -> str:   return st.session_state["user"].id
def get_token() -> str: return st.session_state["session"].access_token
def sessao_ativa() -> bool:
    return "session" in st.session_state and st.session_state["session"] is not None

def _client():
    supabase.postgrest.auth(get_token())
    return supabase

# ─────────────────────────────────────────────────────────────────────────────
# HELPER — converter tipos numpy para JSON serializable
# ─────────────────────────────────────────────────────────────────────────────

def _native(v):
    if isinstance(v, np.integer): return int(v)
    if isinstance(v, np.floating): return float(v)
    if isinstance(v, np.bool_):    return bool(v)
    return v

def _clean(d: dict) -> dict:
    return {k: _native(v) for k, v in d.items()}

# ─────────────────────────────────────────────────────────────────────────────
# PERFIL DO ATLETA — Supabase
# ─────────────────────────────────────────────────────────────────────────────

def carregar_perfil() -> dict | None:
    try:
        res = _client().table("perfil_atleta").select("*").eq("user_id", get_uid()).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        st.error(f"Erro ao carregar perfil: {e}")
        return None

def salvar_perfil(dados: dict) -> None:
    try:
        payload = _clean({**dados, "user_id": get_uid(), "updated_at": datetime.now().isoformat()})
        _client().table("perfil_atleta").upsert(payload, on_conflict="user_id").execute()
        st.session_state["perfil"] = payload
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Erro ao salvar perfil: {e}")

def calcular_idade(data_nasc_str: str) -> int:
    if not data_nasc_str:
        return 0
    try:
        dn = datetime.strptime(str(data_nasc_str), "%Y-%m-%d").date()
        hoje = date.today()
        return hoje.year - dn.year - ((hoje.month, hoje.day) < (dn.month, dn.day))
    except:
        return 0

# ─────────────────────────────────────────────────────────────────────────────
# REGISTROS DIÁRIOS — Supabase
# ─────────────────────────────────────────────────────────────────────────────

COLS_SB = [
    "data","peso","bf_atual","carga_treino","vfc_atual","sleep_score",
    "recovery_time","fc_repouso","fase_historica","estrategia_dieta",
    "calorias","carboidratos","proteinas","gorduras",
]
RENAME = {
    "data":"Data","peso":"Peso","bf_atual":"BF_Atual","carga_treino":"Carga_Treino",
    "vfc_atual":"VFC_Atual","sleep_score":"Sleep_Score","recovery_time":"Recovery_Time",
    "fc_repouso":"FC_Repouso","fase_historica":"Fase_Historica",
    "estrategia_dieta":"Estrategia_Dieta","calorias":"Calorias",
    "carboidratos":"Carboidratos","proteinas":"Proteinas","gorduras":"Gorduras",
}

def carregar_registros() -> pd.DataFrame:
    try:
        res = _client().table("registros_atleta").select(",".join(COLS_SB)).order("data").execute()
        if res.data:
            return pd.DataFrame(res.data).rename(columns=RENAME)
        return pd.DataFrame(columns=list(RENAME.values()))
    except Exception as e:
        st.error(f"Erro ao carregar registros: {e}")
        return pd.DataFrame(columns=list(RENAME.values()))

def salvar_registro(dados: dict) -> None:
    try:
        payload = _clean({
            "user_id": get_uid(),
            "data": dados["Data"], "peso": dados["Peso"], "bf_atual": dados["BF_Atual"],
            "carga_treino": dados["Carga_Treino"], "vfc_atual": dados["VFC_Atual"],
            "sleep_score": dados["Sleep_Score"], "recovery_time": dados["Recovery_Time"],
            "fc_repouso": dados["FC_Repouso"], "fase_historica": dados["Fase_Historica"],
            "estrategia_dieta": dados["Estrategia_Dieta"], "calorias": dados["Calorias"],
            "carboidratos": dados["Carboidratos"], "proteinas": dados["Proteinas"],
            "gorduras": dados["Gorduras"],
        })
        _client().table("registros_atleta").upsert(payload, on_conflict="user_id,data").execute()
        st.toast("✅ Registro salvo!", icon="💾")
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

def deletar_registro(data_str: str) -> None:
    try:
        _client().table("registros_atleta").delete().eq("user_id", get_uid()).eq("data", data_str).execute()
        st.toast("🗑️ Registro deletado.")
    except Exception as e:
        st.error(f"Erro ao deletar: {e}")


# ─── Medidas Semanais ─────────────────────────────────────────────────────────

def carregar_ultima_medida_semanal() -> dict:
    """Retorna o registro mais recente de medidas_atleta do usuário."""
    if "ultima_medida" in st.session_state:
        return st.session_state["ultima_medida"]
    try:
        res = _client().table("medidas_atleta").select("*") \
            .eq("user_id", get_uid()).order("data", desc=True).limit(1).execute()
        m = res.data[0] if res.data else {}
        st.session_state["ultima_medida"] = m
        return m
    except Exception:
        return {}


def salvar_medida_semanal(dados: dict) -> None:
    try:
        payload = _clean({**dados, "user_id": get_uid()})
        _client().table("medidas_atleta").insert(payload).execute()
        st.toast("✅ Medidas salvas!", icon="📏")
        if "ultima_medida" in st.session_state:
            del st.session_state["ultima_medida"]
    except Exception as e:
        st.error(f"Erro ao salvar medidas: {e}")


def deletar_medida_semanal(record_id: str) -> None:
    try:
        _client().table("medidas_atleta").delete() \
            .eq("id", record_id).eq("user_id", get_uid()).execute()
        st.toast("🗑️ Medida deletada.")
        if "ultima_medida" in st.session_state:
            del st.session_state["ultima_medida"]
    except Exception as e:
        st.error(f"Erro ao deletar: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — renderizar referências
# ─────────────────────────────────────────────────────────────────────────────

CORES_MOD = {
    "Periodização":"#6C63FF","Nutrição":"#FF6B6B","Treino":"#4ECDC4",
    "Recuperação":"#FFD166","Suplementação":"#A8DADC",
}

def _render_refs(modulo: str, card: bool = False):
    cor = CORES_MOD.get(modulo, "#888")
    for ref in get_refs_por_modulo(modulo):
        if card:
            st.markdown(
                f"<div style='border-left:4px solid {cor};padding:8px 12px;"
                f"margin-bottom:10px;background:rgba(0,0,0,0.03);border-radius:4px;'>"
                f"<b style='font-size:0.88em'>{ref['apa']}</b><br>"
                f"<i style='color:#555;font-size:0.82em'>💡 {ref['resumo']}</i></div>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f"<span style='background:{ref['badge_color']};color:white;padding:2px 8px;"
                f"border-radius:8px;font-size:0.78em'>{ref['modulo']}</span> "
                f"{ref['apa']}<br><i style='color:gray;font-size:0.82em'>{ref['resumo']}</i><br><br>",
                unsafe_allow_html=True,
            )

# ─────────────────────────────────────────────────────────────────────────────
# TELA DE AUTH
# ─────────────────────────────────────────────────────────────────────────────

def render_tela_auth():
    st.title("🧬 Pro Coach IA")
    st.caption("Periodização científica para atletas IFBB Pro — baseada em literatura peer-reviewed.")
    st.divider()

    aba_login, aba_cad = st.tabs(["🔐 Entrar", "📝 Criar conta"])

    with aba_login:
        st.markdown("### Entre na sua conta")
        email = st.text_input("E-mail", key="login_email")
        senha = st.text_input("Senha", type="password", key="login_senha")
        if st.button("Entrar", type="primary", use_container_width=True, key="btn_login"):
            if email and senha:
                if fazer_login(email, senha):
                    st.rerun()
            else:
                st.warning("Preencha e-mail e senha.")

    with aba_cad:
        st.markdown("### Criar conta gratuita")
        ec  = st.text_input("E-mail", key="cad_email")
        sc  = st.text_input("Senha", type="password", placeholder="Mínimo 6 caracteres", key="cad_senha")
        sc2 = st.text_input("Confirmar senha", type="password", key="cad_senha2")
        if st.button("Criar conta", use_container_width=True, key="btn_cad"):
            if not ec or not sc:        st.warning("Preencha todos os campos.")
            elif sc != sc2:             st.error("❌ Senhas não coincidem.")
            elif len(sc) < 6:          st.error("❌ Senha muito curta.")
            else:                       fazer_cadastro(ec, sc)

    st.divider()
    st.caption("⚕️ Ferramenta educacional — não substitui avaliação profissional.")

# ─────────────────────────────────────────────────────────────────────────────
# TELA DE ONBOARDING (primeiro acesso)
# ─────────────────────────────────────────────────────────────────────────────

def render_onboarding():
    st.title("🧬 Bem-vindo ao Pro Coach IA!")
    st.info("Para personalizar suas recomendações, preencha seu perfil de atleta. **Você só fará isso uma vez.**")
    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("👤 Dados Pessoais")
        nome        = st.text_input("Nome completo")
        data_nasc   = st.date_input("Data de nascimento",
                        value=date(1990, 1, 1), min_value=date(1950,1,1), max_value=date.today())
        sexo        = st.radio("Sexo biológico", ["Masculino","Feminino"], horizontal=True)
        altura      = st.number_input("Altura (cm)", min_value=140, max_value=230, value=178)
        anos_treino = st.number_input("Anos de treino com pesos", min_value=0, max_value=40, value=5)

    with col2:
        st.subheader("🏆 Dados Competitivos")
        categoria   = st.selectbox("Categoria alvo",
                        ["Mens Physique","Classic Physique","Bodybuilding Open","Bikini","Wellness","Physique Feminino"])
        uso_peds    = st.checkbox("Uso de PEDs / TRT")
        bf_alvo     = st.number_input("% BF alvo no palco", min_value=2.0, max_value=20.0, value=5.0, step=0.5)
        data_comp   = st.date_input("Data da próxima competição",
                        value=date.today() + timedelta(days=120))
        vfc_base    = st.number_input("VFC Baseline (média 7 dias, ms)", min_value=20.0, max_value=120.0, value=60.0, step=1.0)

    st.divider()
    if st.button("💾 Salvar Perfil e Entrar no App", type="primary", use_container_width=True):
        if not nome:
            st.warning("Informe seu nome.")
        else:
            salvar_perfil({
                "nome": nome,
                "data_nasc": str(data_nasc),
                "sexo": sexo,
                "altura": float(altura),
                "anos_treino": int(anos_treino),
                "categoria": categoria,
                "uso_peds": bool(uso_peds),
                "bf_alvo": float(bf_alvo),
                "data_competicao": str(data_comp),
                "vfc_baseline": float(vfc_base),
            })
            st.success("✅ Perfil salvo! Carregando app...")
            st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR — só dados diários de recuperação + perfil colapsável
# ─────────────────────────────────────────────────────────────────────────────

def render_sidebar(perfil: dict):
    st.sidebar.markdown(f"### 👤 {perfil.get('nome','Atleta')}")
    st.sidebar.caption(f"{st.session_state['user'].email}")
    if st.sidebar.button("Sair", use_container_width=True):
        fazer_logout()

    st.sidebar.divider()

    # ── Perfil colapsável ─────────────────────────────────────────────────────
    with st.sidebar.expander("⚙️ Perfil do Atleta", expanded=False):
        nome_e      = st.text_input("Nome", value=perfil.get("nome",""), key="sb_nome")
        dn_val      = datetime.strptime(str(perfil.get("data_nasc","1990-01-01")), "%Y-%m-%d").date()
        data_nasc_e = st.date_input("Data de nascimento", value=dn_val, key="sb_nasc")
        sexo_e      = st.radio("Sexo", ["Masculino","Feminino"],
                        index=0 if perfil.get("sexo","Masculino")=="Masculino" else 1, key="sb_sexo")
        altura_e    = st.number_input("Altura (cm)", value=float(perfil.get("altura",178)), key="sb_alt")
        cat_opts    = ["Mens Physique","Classic Physique","Bodybuilding Open","Bikini","Wellness","Physique Feminino"]
        cat_idx     = cat_opts.index(perfil.get("categoria","Mens Physique")) if perfil.get("categoria") in cat_opts else 0
        cat_e       = st.selectbox("Categoria", cat_opts, index=cat_idx, key="sb_cat")
        peds_e      = st.checkbox("Uso de PEDs", value=bool(perfil.get("uso_peds",False)), key="sb_peds")
        bf_alvo_e   = st.number_input("% BF Alvo", value=float(perfil.get("bf_alvo",5.0)), step=0.5, key="sb_bf")
        anos_e      = st.number_input("Anos de treino", value=int(perfil.get("anos_treino",5)), key="sb_anos")
        dc_val      = datetime.strptime(str(perfil.get("data_competicao", str(date.today()+timedelta(days=120)))), "%Y-%m-%d").date()
        data_comp_e = st.date_input("Data da competição", value=dc_val, key="sb_comp")
        vfc_base_e  = st.number_input("VFC Baseline (ms)", value=float(perfil.get("vfc_baseline",60.0)), key="sb_vfc")

        if st.button("💾 Atualizar Perfil", use_container_width=True, key="btn_perfil"):
            salvar_perfil({
                "nome": nome_e, "data_nasc": str(data_nasc_e), "sexo": sexo_e,
                "altura": float(altura_e), "categoria": cat_e, "uso_peds": bool(peds_e),
                "bf_alvo": float(bf_alvo_e), "anos_treino": int(anos_e),
                "data_competicao": str(data_comp_e), "vfc_baseline": float(vfc_base_e),
            })
            st.rerun()

        idade_calc = calcular_idade(str(data_nasc_e))
        st.info(f"🎂 Idade atual: **{idade_calc} anos**")

    st.sidebar.divider()

    # ── Registro diário — SOMENTE dados de recuperação Garmin ────────────────
    st.sidebar.header("📡 Registro Diário de Recuperação")
    st.sidebar.caption("Peso, BF% e medidas → aba **Registros**")

    # Pré-carregar valores se linha selecionada na tabela histórico
    sel = st.session_state.get("linha_selecionada")
    def_data  = datetime.strptime(str(sel["Data"]), "%Y-%m-%d").date() if sel else date.today()
    def_carga = float(sel["Carga_Treino"]) if sel else 300.0
    def_vfc   = float(sel["VFC_Atual"])    if sel else 60.0
    def_sleep = int(sel["Sleep_Score"])    if sel else 75
    def_rec   = int(sel["Recovery_Time"])  if sel else 24
    def_fc    = int(sel["FC_Repouso"])     if sel else 55

    # BUG FIX: não usar key fixa para data_reg quando há seleção —
    # os widgets com key persistem o valor anterior no session_state.
    # Forçar o valor correto via key única quando troca de row.
    data_key = f"sb_data_reg_{str(def_data)}"
    data_reg = st.sidebar.date_input("Data do Registro", value=def_data, key=data_key)

    carga_tr  = st.sidebar.number_input("Volume Load (kg×reps)", value=def_carga, step=10.0, key="sb_carga")
    vfc_at    = st.sidebar.number_input("VFC Noturna (ms)", value=def_vfc, step=1.0, key="sb_vfc_at")
    sleep_sc  = st.sidebar.slider("Sleep Score", 0, 100, def_sleep, key="sb_sleep")
    rec_time  = st.sidebar.number_input("Recovery Time (h)", value=def_rec, step=1, key="sb_rec")
    fc_rep    = st.sidebar.number_input("FC Repouso (bpm)", value=def_fc, step=1, key="sb_fc")

    # Perfil resolvido (prioriza widget se já foi aberto, caso contrário usa perfil salvo)
    sexo     = st.session_state.get("sb_sexo",     perfil.get("sexo","Masculino"))
    categoria= st.session_state.get("sb_cat",      perfil.get("categoria","Mens Physique"))
    bf_alvo  = float(st.session_state.get("sb_bf", perfil.get("bf_alvo",5.0)))
    data_comp= st.session_state.get("sb_comp",     dc_val)
    uso_peds = bool(st.session_state.get("sb_peds",perfil.get("uso_peds",False)))
    vfc_base = float(st.session_state.get("sb_vfc",perfil.get("vfc_baseline",60.0)))
    idade    = calcular_idade(str(st.session_state.get("sb_nasc", dn_val)))
    anos_tr  = int(st.session_state.get("sb_anos", perfil.get("anos_treino",5)))
    altura   = float(st.session_state.get("sb_alt", perfil.get("altura",178.0)))

    return {
        "data_reg": data_reg,
        "carga_tr": carga_tr, "vfc_at": vfc_at, "sleep_sc": sleep_sc,
        "rec_time": rec_time, "fc_rep": fc_rep,
        "sexo": sexo, "categoria": categoria, "bf_alvo": bf_alvo,
        "data_comp": data_comp, "uso_peds": uso_peds, "vfc_base": vfc_base,
        "idade": idade, "anos_treino": anos_tr, "altura": altura,
    }

# ─────────────────────────────────────────────────────────────────────────────
# ABAS DO APP
# ─────────────────────────────────────────────────────────────────────────────

def tab_dashboard(p, atleta, flags, fase, df_hist, df_timeline, dieta_hoje, df_dieta):
    st.header("🏠 Dashboard do Dia")

    # Métricas principais
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Fase", fase)
    c2.metric("Dias p/ Show", f"{max(0,(p['data_comp']-date.today()).days)}d")
    taxa = f"{flags['taxa_perda_peso']:.2f}%/sem" if flags.get("taxa_perda_peso") else "—"
    c3.metric("Taxa Perda", taxa)
    c4.metric("Peso Atual", f"{p['peso_at']} kg")
    c5.metric("BF Atual", f"{p['bf_at']}%")

    if flags.get("plato_metabolico"):
        st.error("🚨 **PLATÔ METABÓLICO** — Taxa < 0.5%/sem por 2 semanas. Protocolo de quebra ativado. *(Peos et al., 2019)*")

    st.divider()

    # Status de recuperação resumido
    (status_dia, acao_dia, motivo_dia, painel,
     acwr_val, acwr_status, cv_val, cv_status) = prescrever_treino_do_dia(atleta, df_hist)

    fn = st.error if "Severa" in status_dia else (st.warning if "Incompleta" in status_dia else st.success)
    fn(f"**{status_dia}** — {acao_dia}")
    st.caption(f"*{motivo_dia}*")

    st.divider()

    # Macros do dia
    st.subheader(f"🍽️ Alvo Nutricional de Hoje — {dieta_hoje['Estratégia']}")
    mc1,mc2,mc3,mc4 = st.columns(4)
    mc1.metric("Calorias", f"{dieta_hoje['Calorias']} kcal")
    mc2.metric("Proteína", f"{dieta_hoje['Prot(g)']}g")
    mc3.metric("Carboidrato", f"{dieta_hoje['Carb(g)']}g")
    mc4.metric("Gordura", f"{dieta_hoje['Gord(g)']}g")

    st.divider()

    # Histórico — tabela CRUD
    st.subheader("💾 Histórico de Registros")
    st.caption("Clique em uma linha para pré-carregar na sidebar (modo edição).")
    df_disp = df_hist.sort_values("Data", ascending=False) if not df_hist.empty else df_hist
    ev = st.dataframe(df_disp, on_select="rerun", selection_mode="single-row", use_container_width=True)
    if not df_hist.empty and len(ev.selection.rows) > 0:
        st.session_state["linha_selecionada"] = df_disp.iloc[ev.selection.rows[0]].to_dict()
    else:
        st.session_state["linha_selecionada"] = None


def tab_periodizacao(fase, df_timeline, flags, p, atleta, df_hist):
    st.header("🗓️ Periodização")

    c1,c2,c3 = st.columns(3)
    c1.metric("Fase Atual", fase)
    c2.metric("Dias para o Show", f"{max(0,(p['data_comp']-date.today()).days)}d")
    taxa = f"{flags['taxa_perda_peso']:.2f}%/sem" if flags.get("taxa_perda_peso") else "Dados insuficientes"
    c3.metric("Taxa de Perda", taxa)

    if flags.get("plato_metabolico"):
        st.error("🚨 **PLATÔ METABÓLICO DETECTADO** *(Peos et al., 2019)*")
        st.info("**Protocolo recomendado:** Diet break de 1-2 semanas com calorias na manutenção "
                "para restaurar leptina e metabolismo adaptativo. *(Trexler et al., 2014)*")

    if not df_timeline.empty:
        fig = px.timeline(df_timeline, x_start="Inicio", x_end="Fim", y="Fase",
            color="Fase", color_discrete_sequence=px.colors.qualitative.Pastel)
        fig.add_vline(x=datetime.today().strftime("%Y-%m-%d"), line_width=3, line_dash="dash", line_color="red")
        fig.add_annotation(x=datetime.today().strftime("%Y-%m-%d"), y=1.05, yref="paper",
            text="HOJE", showarrow=False, font=dict(color="red",size=14), bgcolor="rgba(255,255,255,0.8)")
        fig.update_yaxes(autorange="reversed")
        st.plotly_chart(fig, use_container_width=True)

    st.divider()
    st.subheader("📖 Fundamentos Científicos da Periodização")

    with st.expander("DUP — Daily Undulating Periodization", expanded=True):
        st.markdown("""
**Rhea et al. (2002)** demonstraram que a periodização ondulatória diária (DUP) produz ganhos
de força significativamente superiores à periodização linear em atletas treinados, por variar
estímulo de intensidade e volume dentro da mesma semana.

**Fases implementadas no sistema:**
- 🔵 **Bulking** → Volume MAV (12-20 séries/músculo/semana), RIR 1-2, progressão +2.5%/semana
- 🔴 **Cutting** → Volume MEV-MAV (8-12 séries), RIR 0-1, manter carga
- 🟡 **Recomposição** → Volume intermediário (10-16 séries), RIR 1-2
- ⚡ **Peak Week** → Volume MEV (6-8 séries), RIR 3-4, depleção → supercompensação
- 🟢 **Off-Season** → Recuperação ativa, volume MEV
        """)

    with st.expander("Detecção de Platô Metabólico"):
        st.markdown("""
Sistema detecta automaticamente platô quando taxa de perda de peso < 0.5%/semana
por 14 dias consecutivos *(Peos et al., 2019)*.

**Resposta fisiológica ao déficit prolongado *(Trexler et al., 2014)*:**
- Redução de leptina → aumento de grelina → aumento de apetite
- Redução de T3 ativo → queda de TMB de até 15-20%
- Aumento de eficiência metabólica → menor gasto em atividade espontânea (NEAT)

**Estratégias de quebra de platô implementadas:**
1. Diet break 1-2 semanas em manutenção
2. Refeed day semanal com carboidratos elevados
3. Ajuste calórico de -150kcal adicional se sem resposta em 7 dias
        """)

    with st.expander("📚 Referências — Periodização"):
        _render_refs("Periodização", card=True)


def tab_nutricao(fase, atleta, df_hist, flags, df_dieta, motivo_dieta, alertas, dieta_hoje, p):
    st.header("🍽️ Nutrição Adaptativa")

    # Alertas adaptativos
    for key, msg in alertas.items():
        if key == "get_base":        st.caption(f"⚙️ {msg}")
        elif "⚠️" in msg or "🔴" in msg: st.warning(msg)

    col_n, col_z = st.columns([2,1])

    with col_n:
        st.subheader(f"Plano Semanal — {fase}")
        st.caption(motivo_dieta)
        st.markdown(
            f"**HOJE ({dieta_hoje['Dia']}):** {dieta_hoje['Estratégia']} → "
            f"**{dieta_hoje['Calorias']} kcal** | "
            f"P: {dieta_hoje['Prot(g)']}g | C: {dieta_hoje['Carb(g)']}g | G: {dieta_hoje['Gord(g)']}g"
        )
        st.dataframe(df_dieta, use_container_width=True, hide_index=True)

    with col_z:
        st.subheader("🏃 Zonas FC (Karvonen)")
        zonas = calcular_zonas_karvonen(p["idade"], p["fc_rep"])
        emj = {"Zona 1 (Recuperação Ativa)":"🔵","Zona 2 (LISS / Fat-Burning)":"🟢",
               "Zona 3 (Aeróbio Moderado)":"🟡","Zona 4 (Limiar Anaeróbio)":"🟠","Zona 5 (HIIT / Máximo)":"🔴"}
        for z,(mn,mx) in zonas.items():
            st.write(f"{emj.get(z,'')} **{z}:** {mn}–{mx} bpm")

    st.divider()
    st.subheader("📖 Fundamentos Científicos da Nutrição")

    with st.expander("Proteína por Massa Magra — Helms et al. (2014)", expanded=True):
        lbm = atleta.peso * (1 - atleta.bf_atual/100)
        prot_min = round(lbm * (2.4 if fase in ["Cutting","Peak Week"] else 1.6), 1)
        prot_max = round(lbm * (3.1 if fase in ["Cutting","Peak Week"] else 2.2), 1)
        st.markdown(f"""
Calculamos proteína pela **Massa Magra (LBM = {lbm:.1f}kg)**, não pelo peso total.
Isso garante precisão em atletas com BF% alto ou baixo.

**Alvo atual:** {prot_min}–{prot_max}g/dia
- 🔴 Cutting/Peak Week: 2.4–3.1g/kg LBM *(Helms et al., 2014)*
- 🔵 Bulking: 1.6–2.2g/kg LBM *(Morton et al., 2018)*

**Por que mais proteína no cutting?** Preservação de massa magra em déficit calórico
e efeito termogênico da proteína (~25% das kcal consumidas).
        """)

    with st.expander("Termogênese Adaptativa — Trexler et al. (2014)"):
        st.markdown("""
Após 4 semanas em déficit, o metabolismo reduz ~15kcal/semana adicionais além
da perda de massa. O sistema aplica esta correção automaticamente para evitar
estagnação por superestimar o GET.

**Mecanismos fisiológicos:**
- Redução de T3 ativo (hormônio tireoidiano)
- Queda de leptina → sinalização de fome aumentada
- Redução do NEAT (Non-Exercise Activity Thermogenesis)
- Aumento da eficiência mitocondrial
        """)

    with st.expander("Ciclagem de Carboidratos 5:2 — Campbell et al. (2020)"):
        st.markdown("""
No cutting, implementamos 5 dias com carboidratos moderados e 2 dias com
carboidratos altos (refeed), o que preserva leptina e performance melhor
que restrição contínua de carboidratos.

**Protocolo Peak Week — Chappell et al. (2018):**
1. Dias 1-3: depleção de carboidratos + treinamento de alto volume
2. Dias 4-5: supercompensação com carboidratos altos (8-10g/kg)
3. Dia 6-7: manutenção com sódio controlado para estética
        """)

    with st.expander("📚 Referências — Nutrição"):
        _render_refs("Nutrição", card=True)


def tab_treino(fase, atleta, df_hist):
    st.header("🏋️ Plano de Treino Semanal")
    df_treino, motivo = gerar_treino_semanal(atleta, exercicios_db)
    st.caption(motivo)
    st.dataframe(df_treino, use_container_width=True, hide_index=True)
    st.download_button("📥 Exportar CSV",
        data=df_treino.to_csv(sep=";", index=False),
        file_name=f"treino_{fase.lower().replace(' ','_')}.csv", mime="text/csv")

    st.divider()
    st.subheader("📖 Fundamentos Científicos do Treino")

    with st.expander("MEV / MAV / MRV — Israetel et al. (2019)", expanded=True):
        vol = {"Bulking":{"MEV":10,"MAV":18,"MRV":22},"Cutting":{"MEV":6,"MAV":10,"MRV":14},
               "Peak Week":{"MEV":4,"MAV":7,"MRV":10},"Recomposição":{"MEV":8,"MAV":14,"MRV":18},
               "Off-Season":{"MEV":4,"MAV":8,"MRV":12}}.get(fase,{"MEV":8,"MAV":14,"MRV":18})
        st.markdown(f"""
**Landmarks de Volume — Fase: {fase}**

| Landmark | Séries/músculo/semana | Significado |
|---|---|---|
| MEV | {vol['MEV']} | Mínimo para manter adaptações |
| **MAV** | **{vol['MAV']}** | **Alvo atual — máximo adaptativo** |
| MRV | {vol['MRV']} | Limite antes do overreaching |

**RIR alvo desta fase:** {"1-2 (Bulking)" if fase=="Bulking" else "0-1 (Cutting/Peak)" if fase in ["Cutting","Peak Week"] else "1-2"}
*(Zourdos et al., 2016)*
        """)

    with st.expander("Variação de Exercícios — Fonseca et al. (2014)"):
        st.markdown("""
Exercícios são selecionados aleatoriamente a cada semana dentro do grupo muscular,
pois variações de ângulo e posição de resistência recrutam diferentes porções
musculares, maximizando hipertrofia total ao longo do macrociclo.

**Técnicas de intensidade por fase *(Schoenfeld 2011, Weakley 2017)*:**
- 🔵 **Bulking:** Drop-sets e Rest-Pause no último exercício de cada grupo
- 🔴 **Cutting:** Supersets antagonistas (maior densidade, menos tempo)
- ⚡ **Peak Week:** Sem técnicas de intensidade — foco em depleção controlada
        """)

    with st.expander("Progressão de Carga — Ralston et al. (2017)"):
        st.markdown("""
**+2.5% de carga por semana** no bulking e recomposição, quando o atleta completa
todas as séries e repetições prescritas no limite superior do RIR.

**Princípio da Sobrecarga Progressiva:**
Sem aumento progressivo de tensão mecânica, o músculo não tem estímulo para
sintetizar novas proteínas contráteis. O sistema rastreia isso via Volume Load
(kg × reps × séries) registrado diariamente.
        """)

    with st.expander("📚 Referências — Treino"):
        _render_refs("Treino", card=True)


def tab_recuperacao(atleta, df_hist, p):
    st.header("🎯 Recuperação e VFC")

    (status_dia, acao_dia, motivo_dia, painel,
     acwr_val, acwr_status, cv_val, cv_status) = prescrever_treino_do_dia(atleta, df_hist)

    st.caption(painel)
    col_s, col_a, col_c = st.columns(3)

    with col_s:
        st.subheader("📋 Status do Dia")
        fn = st.error if "Severa" in status_dia else (st.warning if "Incompleta" in status_dia else st.success)
        fn(f"**{status_dia}**")
        fn(f"**AÇÃO:** {acao_dia}")
        st.info(f"**POR QUÊ?** {motivo_dia}")

    with col_a:
        st.subheader("⚖️ ACWR")
        if acwr_val is not None:
            fig_g = go.Figure(go.Indicator(
                mode="gauge+number", value=acwr_val,
                title={"text":"Acute:Chronic Workload Ratio"},
                gauge={"axis":{"range":[0,2.5]},"bar":{"color":"darkblue"},
                    "steps":[{"range":[0,0.8],"color":"#4FC3F7"},{"range":[0.8,1.3],"color":"#81C784"},
                             {"range":[1.3,1.5],"color":"#FFD54F"},{"range":[1.5,2.5],"color":"#E57373"}],
                    "threshold":{"line":{"color":"red","width":4},"thickness":0.75,"value":1.5}},
            ))
            fig_g.update_layout(height=220, margin=dict(l=10,r=10,t=40,b=10))
            st.plotly_chart(fig_g, use_container_width=True)
        st.caption(acwr_status)

    with col_c:
        st.subheader("📊 CV da VFC (7d)")
        if cv_val is not None:
            cor = "#E57373" if cv_val>10 else ("#FFD54F" if cv_val>7 else "#81C784")
            st.markdown(f"<h1 style='text-align:center;color:{cor}'>{cv_val}%</h1>", unsafe_allow_html=True)
        st.caption(cv_status)

    st.divider()
    st.subheader("📖 Fundamentos Científicos da Recuperação")

    with st.expander("VFC como Indicador de Recuperação do SNC — Flatt & Esco (2016)", expanded=True):
        vfc_b = p["vfc_base"]
        vfc_a = p["vfc_at"]
        delta = round(((vfc_a - vfc_b) / vfc_b) * 100, 1) if vfc_b > 0 else 0
        cor_delta = "🟢" if delta >= -5 else ("🟡" if delta >= -10 else "🔴")
        st.markdown(f"""
**VFC Baseline:** {vfc_b} ms | **VFC Atual:** {vfc_a} ms | **Δ:** {cor_delta} {delta:+.1f}%

A Variabilidade da Frequência Cardíaca reflete o equilíbrio simpático/parassimpático.
Quedas > 10% em relação à baseline indicam fadiga autonômica do SNC,
não apenas fadiga muscular periférica.

**Sistema de pontuação de fadiga (0-10 pontos):**
- VFC < 10% abaixo da baseline → +2 pts
- VFC < 20% abaixo da baseline → +3 pts
- Sleep Score < 60 → +2 pts
- Recovery Time > 72h → +2 pts
- ACWR > 1.5 → +1 pt
- CV-VFC > 10% → +1 pt

**Decisão:** ≥5 pts = repouso total | 3-4 pts = cardio leve (Zona 2) | <3 pts = treinar
        """)

    with st.expander("ACWR — Gabbett (2016) e Hulin et al. (2016)"):
        st.markdown(f"""
**Acute:Chronic Workload Ratio = Carga aguda (7d) ÷ Carga crônica (28d)**

| Zona | ACWR | Interpretação |
|---|---|---|
| 🔵 Subtreino | < 0.8 | Carga insuficiente — risco de perda de adaptações |
| 🟢 Ótimo | 0.8–1.3 | Zona segura de adaptação |
| 🟡 Atenção | 1.3–1.5 | Monitorar sinais de overreaching |
| 🔴 Perigo | > 1.5 | Alto risco de lesão e overtraining |

**ACWR atual: {f"{acwr_val:.2f}" if acwr_val else "dados insuficientes (mín. 7 registros)"}**
        """)

    with st.expander("📚 Referências — Recuperação"):
        _render_refs("Recuperação", card=True)


def tab_suplementacao(atleta):
    st.header("💊 Suplementação")
    st.caption("Apenas suplementos com evidência Grau A ou B incluídos.")
    st.dataframe(recomendar_suplementos(atleta), use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("📖 Fundamentos Científicos da Suplementação")

    with st.expander("Creatina Monoidratada — Kreider et al. (2017)", expanded=True):
        st.markdown("""
**Dose:** 3–5g/dia, uso contínuo sem necessidade de ciclar.

Suplemento com maior body of evidence em esportes de força. Aumenta PCr intramuscular,
permitindo maior ressíntese de ATP durante esforços máximos curtos.
Efeitos: +5-15% em força, +1-2kg de massa magra no longo prazo.

**Timing:** qualquer horário — o efeito é de saturação muscular crônica, não agudo.
        """)

    with st.expander("Cafeína — Grgic et al. (2019)"):
        st.markdown("""
**Dose:** 3–6mg/kg de peso corporal, 45-60min pré-treino.

Bloqueia receptores de adenosina → reduz percepção de esforço e fadiga central.
Melhora performance em força, resistência muscular e potência.

**Atenção:** tolerância se desenvolve com uso diário — ciclar ou usar só em treinos
de alta intensidade maximiza o efeito ergogênico.
        """)

    with st.expander("Beta-Alanina — Hobson et al. (2012)"):
        st.markdown("""
**Dose:** 3.2–6.4g/dia em doses divididas (para minimizar parestesia).

Precursor de carnosina intramuscular → tamponamento de H+ → reduz acidose
metabólica → aumenta capacidade de trabalho em séries de 8-15 reps.

Especialmente útil em treinos de alto volume (cutting e bulking com drop-sets).
        """)

    with st.expander("📚 Referências — Suplementação"):
        _render_refs("Suplementação", card=True)


def tab_evolucao(df_hist):
    st.header("📈 Análise de Evolução")

    if df_hist.empty or len(df_hist) < 2:
        st.info("📊 Registre pelo menos 2 dias de dados para visualizar os gráficos.")
        return

    df_p = df_hist.sort_values("Data")

    # VFC vs Carga
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_p["Data"], y=df_p["VFC_Atual"].astype(float),
        mode="lines+markers", name="VFC (ms)", yaxis="y1",
        line=dict(color="#00e676",width=2), marker=dict(size=6)))
    fig.add_trace(go.Bar(x=df_p["Data"], y=df_p["Carga_Treino"].astype(float),
        name="Volume Load", yaxis="y2", opacity=0.4, marker_color="#EF5350"))
    fig.update_layout(
        title="VFC vs Volume de Treino (Correlação SNC)",
        yaxis=dict(title=dict(text="VFC (ms)",font=dict(color="#00e676")),tickfont=dict(color="#00e676")),
        yaxis2=dict(title=dict(text="Volume Load",font=dict(color="#EF5350")),
            tickfont=dict(color="#EF5350"),overlaying="y",side="right"),
        plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",legend=dict(orientation="h",y=1.1,x=1,xanchor="right"),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Peso vs BF
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(x=df_p["Data"], y=df_p["Peso"].astype(float),
        mode="lines+markers", name="Peso (kg)", yaxis="y1", line=dict(color="#42A5F5",width=2)))
    fig2.add_trace(go.Scatter(x=df_p["Data"], y=df_p["BF_Atual"].astype(float),
        mode="lines+markers", name="BF %", yaxis="y2", line=dict(color="#FFA726",width=2,dash="dash")))
    fig2.update_layout(
        title="Evolução de Peso e % BF",
        yaxis=dict(title=dict(text="Peso (kg)",font=dict(color="#42A5F5")),tickfont=dict(color="#42A5F5")),
        yaxis2=dict(title=dict(text="BF %",font=dict(color="#FFA726")),
            tickfont=dict(color="#FFA726"),overlaying="y",side="right"),
        plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",hovermode="x unified",
    )
    st.plotly_chart(fig2, use_container_width=True)

    # Sleep vs Recovery
    if "Sleep_Score" in df_p.columns and "Recovery_Time" in df_p.columns:
        fig3 = go.Figure()
        fig3.add_trace(go.Scatter(x=df_p["Data"], y=df_p["Sleep_Score"].astype(float),
            mode="lines+markers", name="Sleep Score", yaxis="y1", line=dict(color="#CE93D8",width=2)))
        fig3.add_trace(go.Scatter(x=df_p["Data"], y=df_p["Recovery_Time"].astype(float),
            mode="lines+markers", name="Recovery Time (h)", yaxis="y2",
            line=dict(color="#80DEEA",width=2,dash="dot")))
        fig3.update_layout(
            title="Sleep Score vs Recovery Time",
            yaxis=dict(title=dict(text="Sleep Score",font=dict(color="#CE93D8")),tickfont=dict(color="#CE93D8")),
            yaxis2=dict(title=dict(text="Recovery (h)",font=dict(color="#80DEEA")),
                tickfont=dict(color="#80DEEA"),overlaying="y",side="right"),
            plot_bgcolor="rgba(0,0,0,0)",paper_bgcolor="rgba(0,0,0,0)",hovermode="x unified",
        )
        st.plotly_chart(fig3, use_container_width=True)



# ─────────────────────────────────────────────────────────────────────────────
# ABA — MEDIDAS & PROPORÇÕES
# ─────────────────────────────────────────────────────────────────────────────

def tab_registros(p: dict, atleta, perfil: dict, df_historico: pd.DataFrame):
    """
    Aba unificada de todos os registros de dados coletados:
    - Seção A: Peso e BF% semanal (bioimpedância + dobras com seleção inteligente de fórmula)
    - Seção B: Circunferências e dobras cutâneas semanais
    - Seção C: Histórico de registros diários (CRUD)
    - Seção D: Análise de proporções estéticas
    - Seção E: Zonas de FC (manual ergoespirometria ou Karvonen)
    """
    st.header("📁 Registros")
    st.caption("Peso, BF% e medidas são semanais — registre uma vez por semana na mesma condição (manhã, em jejum).")

    categoria = p["categoria"]
    altura_cm = p.get("altura", 178.0)
    sexo      = p.get("sexo", "Masculino")
    idade     = p.get("idade", 30)

    # Carregar última medida
    ultima = carregar_ultima_medida_semanal()

    # ═══════════════════════════════════════════════════════════════════════════
    # SEÇÃO A — PESO E BF%
    # ═══════════════════════════════════════════════════════════════════════════
    st.subheader("⚖️ A — Peso e Composição Corporal")
    st.caption("Preencha semanalmente. O sistema usa esses valores em todos os cálculos.")

    col_peso, col_bf = st.columns(2)

    with col_peso:
        data_med = st.date_input("Data da medição", value=date.today(), key="reg_data")
        peso_sem = st.number_input("Peso (kg)",
            value=float(ultima.get("peso") or 85.0), step=0.1, key="reg_peso")
        st.caption("💡 Pese-se sempre na mesma condição: manhã, após urinar, antes de comer.")

    with col_bf:
        bf_bio = st.number_input(
            "BF% via Bioimpedância",
            value=float(ultima.get("bf_bioimpedancia") or 0.0),
            min_value=0.0, max_value=60.0, step=0.1, key="reg_bf_bio",
            help="Digite o resultado direto do aparelho. 0 = não disponível."
        )
        st.caption("💡 Bioimpedância tem erro de ±3–8%. Use como referência de tendência.")

    # ═══════════════════════════════════════════════════════════════════════════
    # SEÇÃO B — DOBRAS CUTÂNEAS COM SELEÇÃO DE FÓRMULA
    # ═══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("🔬 B — Dobras Cutâneas (mm)")

    with st.expander("Expandir para inserir dobras cutâneas", expanded=False):
        st.caption("Meça com plicômetro. Todas as medidas no lado direito do corpo. Pellizcar bem antes de medir.")

        col_d1, col_d2 = st.columns(2)
        with col_d1:
            d_peit = st.number_input("Peitoral", min_value=0.0, step=0.5,
                value=float(ultima.get("dobra_peitoral") or 0.0), key="dob_peit")
            d_axil = st.number_input("Axilar Média", min_value=0.0, step=0.5,
                value=float(ultima.get("dobra_axilar") or 0.0), key="dob_axil")
            d_tric = st.number_input("Tricipital", min_value=0.0, step=0.5,
                value=float(ultima.get("dobra_tricipital") or 0.0), key="dob_tric")
            d_supr = st.number_input("Suprailíaca", min_value=0.0, step=0.5,
                value=float(ultima.get("dobra_suprailiaca") or 0.0), key="dob_supr")
        with col_d2:
            d_sube = st.number_input("Subescapular", min_value=0.0, step=0.5,
                value=float(ultima.get("dobra_subescapular") or 0.0), key="dob_sube")
            d_abdo = st.number_input("Abdominal", min_value=0.0, step=0.5,
                value=float(ultima.get("dobra_abdominal") or 0.0), key="dob_abdo")
            d_coxa = st.number_input("Coxa", min_value=0.0, step=0.5,
                value=float(ultima.get("dobra_coxa") or 0.0), key="dob_coxa")
            d_bici = st.number_input("Bíceps (para Durnin)", min_value=0.0, step=0.5,
                value=float(ultima.get("dobra_bicipital") or 0.0), key="dob_bici")

        dobras_dict = {
            "dobra_peitoral":d_peit,"dobra_axilar":d_axil,"dobra_tricipital":d_tric,
            "dobra_suprailiaca":d_supr,"dobra_subescapular":d_sube,"dobra_abdominal":d_abdo,
            "dobra_coxa":d_coxa,"dobra_bicipital":d_bici,
        }

        # Sugestão inteligente de fórmula
        sugerida_id, sugerida_just = sugerir_formula_dobras(dobras_dict, sexo, bf_bio or 15.0)
        st.info(f"💡 **Fórmula sugerida:** {FORMULAS_DOBRAS.get(sugerida_id,{}).get('nome',sugerida_id)} — {sugerida_just}")

        # Listar só fórmulas compatíveis com o sexo
        opcoes_formulas = []
        for fid, finfo in FORMULAS_DOBRAS.items():
            campos = finfo["campos_masc"] if sexo == "Masculino" else finfo["campos_fem"]
            if campos:  # fórmula tem campos para este sexo
                opcoes_formulas.append((fid, finfo["nome"]))

        formula_label_to_id = {v: k for k, v in opcoes_formulas}
        labels = [v for _, v in opcoes_formulas]
        default_label = FORMULAS_DOBRAS.get(sugerida_id, {}).get("nome", labels[0])
        if default_label not in labels:
            default_label = labels[0]

        formula_escolhida_label = st.selectbox(
            "Fórmula de cálculo",
            options=labels,
            index=labels.index(default_label),
            key="reg_formula",
            help="O app sugere automaticamente a melhor, mas você pode escolher outra."
        )
        formula_id = formula_label_to_id.get(formula_escolhida_label, "jp7")

        # Calcular BF% pela fórmula escolhida
        bf_calc = calcular_bf_por_formula(formula_id, dobras_dict, idade, sexo)

        if bf_calc is not None:
            lbm_c = round(peso_sem * (1 - bf_calc/100), 1)
            fm_c  = round(peso_sem * (bf_calc/100), 1)
            c1,c2,c3 = st.columns(3)
            c1.metric(f"BF% ({formula_escolhida_label.split('(')[0].strip()})", f"{bf_calc}%")
            c2.metric("LBM", f"{lbm_c}kg")
            c3.metric("FM", f"{fm_c}kg")
            ref = FORMULAS_DOBRAS.get(formula_id,{}).get("referencia","")
            st.caption(f"*{FORMULAS_DOBRAS.get(formula_id,{}).get('descricao','')} — {ref}*")
        else:
            st.warning("Preencha as dobras acima para calcular o BF%.")
            bf_calc = None

    # BF% final: bioimpedância se disponível, dobras como secundário
    bf_final = None
    bf_fonte = "—"
    if bf_calc is not None and bf_bio > 0:
        media = round((bf_calc + bf_bio) / 2, 1)
        bf_final = media
        bf_fonte = f"Média bioimpedância ({bf_bio}%) + dobras ({bf_calc}%) = {media}%"
    elif bf_calc is not None:
        bf_final = bf_calc
        bf_fonte = f"Dobras ({formula_escolhida_label.split('(')[0].strip()}): {bf_calc}%"
    elif bf_bio > 0:
        bf_final = bf_bio
        bf_fonte = f"Bioimpedância: {bf_bio}%"

    if bf_final:
        st.success(f"✅ **BF% usado no sistema: {bf_final}%** — *{bf_fonte}*")

    # ═══════════════════════════════════════════════════════════════════════════
    # SEÇÃO C — CIRCUNFERÊNCIAS
    # ═══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("📐 C — Circunferências (cm)")

    with st.expander("Expandir para inserir circunferências", expanded=False):
        cc1, cc2 = st.columns(2)
        with cc1:
            cintura  = st.number_input("Cintura (nível umbigo)",   min_value=0.0, step=0.5,
                value=float(ultima.get("cintura") or 80.0), key="med_cin")
            ombros   = st.number_input("Ombros (maior circ.)",     min_value=0.0, step=0.5,
                value=float(ultima.get("ombros") or 110.0), key="med_omb")
            peito    = st.number_input("Peito",                    min_value=0.0, step=0.5,
                value=float(ultima.get("peito") or 100.0),  key="med_pei")
            quadril  = st.number_input("Quadril",                  min_value=0.0, step=0.5,
                value=float(ultima.get("quadril") or 95.0), key="med_qua")
        with cc2:
            biceps_d = st.number_input("Bíceps D (contraído)",     min_value=0.0, step=0.5,
                value=float(ultima.get("biceps_d") or 38.0), key="med_bic")
            coxa_d   = st.number_input("Coxa D",                   min_value=0.0, step=0.5,
                value=float(ultima.get("coxa_d") or 56.0),  key="med_cox")
            pant_d   = st.number_input("Panturrilha D",            min_value=0.0, step=0.5,
                value=float(ultima.get("panturrilha_d") or 38.0), key="med_pan")
            pescoco  = st.number_input("Pescoço",                  min_value=0.0, step=0.5,
                value=float(ultima.get("pescoco") or 38.0), key="med_pes")

    # ═══════════════════════════════════════════════════════════════════════════
    # SEÇÃO D — ZONAS DE FC (manual ou Karvonen)
    # ═══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("🫀 D — Zonas de Frequência Cardíaca")

    usar_manual = st.checkbox(
        "Tenho laudo de ergoespirometria com zonas de FC personalizadas",
        value=bool(ultima.get("zona1_min")), key="fc_manual"
    )
    zonas_input = {}
    if usar_manual:
        st.caption("Preencha as zonas do seu laudo. Estas substituem o cálculo de Karvonen em todo o app.")
        nomes_z = ["Z1 Recuperação","Z2 LISS","Z3 Aeróbio","Z4 Limiar","Z5 Máximo"]
        for i in range(1, 6):
            cz1, cz2, cz3 = st.columns([2,1,1])
            cz1.markdown(f"**{nomes_z[i-1]}**")
            zonas_input[f"zona{i}_min"] = cz2.number_input(
                "Min", min_value=0.0, step=1.0,
                value=float(ultima.get(f"zona{i}_min") or 0.0), key=f"z{i}min")
            zonas_input[f"zona{i}_max"] = cz3.number_input(
                "Máx", min_value=0.0, step=1.0,
                value=float(ultima.get(f"zona{i}_max") or 0.0), key=f"z{i}max")
        zonas_man = zonas_fc_manuais(zonas_input)
        if zonas_man:
            st.success("✅ Zonas de ergoespirometria configuradas — usadas em todo o app.")
    else:
        zonas_man = {}
        zonas_kv  = calcular_zonas_karvonen(idade, p.get("fc_rep", 60))
        st.caption("Usando fórmula de Karvonen. Configure ergoespirometria acima para maior precisão.")
        emj = {"Zona 1 (Recuperação Ativa)":"🔵","Zona 2 (LISS / Fat-Burning)":"🟢",
               "Zona 3 (Aeróbio Moderado)":"🟡","Zona 4 (Limiar Anaeróbio)":"🟠","Zona 5 (HIIT / Máximo)":"🔴"}
        for z,(mn,mx) in zonas_kv.items():
            st.write(f"{emj.get(z,'')} **{z}:** {mn}–{mx} bpm")

    notas = st.text_area("Notas desta medição", value="", key="reg_notas", height=60)

    # ── Botão salvar tudo ─────────────────────────────────────────────────────
    st.divider()
    if st.button("💾 Salvar Registro Semanal", type="primary", use_container_width=True, key="btn_salvar_sem"):
        try:
            dobras_save = {
                "dobra_peitoral":d_peit,"dobra_axilar":d_axil,"dobra_tricipital":d_tric,
                "dobra_suprailiaca":d_supr,"dobra_subescapular":d_sube,"dobra_abdominal":d_abdo,
                "dobra_coxa":d_coxa,"dobra_bicipital":d_bici,
            } if 'd_peit' in dir() else {}
        except:
            dobras_save = {}
        try:
            circ_save = {
                "cintura":cintura,"ombros":ombros,"peito":peito,"quadril":quadril,
                "biceps_d":biceps_d,"coxa_d":coxa_d,"panturrilha_d":pant_d,"pescoco":pescoco,
            }
        except:
            circ_save = {}
        payload = {
            "data": str(data_med),
            "peso": float(peso_sem),
            "bf_bioimpedancia": float(bf_bio) if bf_bio > 0 else None,
            "bf_formula": formula_id if bf_calc is not None else None,
            "bf_calculado": float(bf_calc) if bf_calc is not None else None,
            "bf_final": float(bf_final) if bf_final else None,
            "notas": notas,
            **dobras_save,
            **circ_save,
            **zonas_input,
        }
        salvar_medida_semanal(payload)
        st.rerun()

    # ═══════════════════════════════════════════════════════════════════════════
    # SEÇÃO E — ANÁLISE DE PROPORÇÕES
    # ═══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("📊 E — Proporções Estéticas")
    prop_info = PROPORCOES_CATEGORIA.get(categoria, {})
    st.info(f"**{categoria}:** {prop_info.get('descricao','')}")

    try:
        medidas_dict = {
            "cintura":cintura,"ombros":ombros,"peito":peito,
            "quadril":quadril,"biceps_d":biceps_d,"coxa_d":coxa_d,
        }
        proporcoes = avaliar_proporcoes(categoria, medidas_dict, altura_cm)
    except:
        medidas_dict = {}
        proporcoes   = {}

    if proporcoes:
        if "ombro_cintura" in proporcoes:
            r = proporcoes["ombro_cintura"]
            st.markdown("### 🌀 Razão Áurea (φ = 1.618)")
            prog = min(r["atual"] / r["alvo"], 1.0) if r["alvo"] > 0 else 0
            st.progress(prog, text=f"{r['atual']:.3f} / {r['alvo']} — {r['status']}")
            st.caption(r["rec"])

        st.markdown("### Todas as Proporções")
        labels_prop = {
            "cintura":"Cintura","ombro_cintura":"Ombro / Cintura",
            "quadril_cintura":"Quadril / Cintura","peito_cintura":"Peito / Cintura",
            "braco_cintura":"Braço / Cintura",
        }
        for key, dados in proporcoes.items():
            label = labels_prop.get(key, key)
            alvo  = dados.get("alvo") or dados.get("alvo_max", "—")
            st.markdown(
                f"{dados['status']} **{label}** — "
                f"Atual: `{dados.get('atual', '—')}` | "
                f"Alvo: `{alvo}` — *{dados['rec']}*"
            )
    else:
        st.info("Expanda a seção de circunferências e preencha os dados para ver a análise.")

    # ═══════════════════════════════════════════════════════════════════════════
    # SEÇÃO F — HISTÓRICO DE REGISTROS DIÁRIOS
    # ═══════════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("📅 F — Histórico de Registros Diários")
    st.caption("Selecione uma linha para editar ou deletar via sidebar. "
               "Dados diários: VFC, Sleep, Recovery, FC, Volume de Treino.")

    df_disp = df_historico.sort_values("Data", ascending=False) if not df_historico.empty else df_historico
    # Mostrar apenas colunas relevantes para registros diários
    cols_disp = ["Data","Carga_Treino","VFC_Atual","Sleep_Score","Recovery_Time","FC_Repouso","Fase_Historica"]
    cols_ok   = [c for c in cols_disp if c in df_disp.columns]
    ev = st.dataframe(
        df_disp[cols_ok] if cols_ok else df_disp,
        on_select="rerun", selection_mode="single-row", use_container_width=True
    )
    if not df_historico.empty and len(ev.selection.rows) > 0:
        row_sel = df_disp.iloc[ev.selection.rows[0]]
        # Preservar row completo (incluindo Peso/BF_Atual para o payload de update)
        full_row = df_disp.iloc[ev.selection.rows[0]].to_dict()
        st.session_state["linha_selecionada"] = full_row
        st.caption(f"✏️ Linha selecionada: **{full_row.get('Data','')}** — use sidebar para Atualizar ou Deletar.")
    else:
        st.session_state["linha_selecionada"] = None

    # ── Histórico de medidas semanais ─────────────────────────────────────────
    st.divider()
    st.subheader("📈 Histórico de Medidas Semanais")
    try:
        res_h = _client().table("medidas_atleta").select(
            "id,data,peso,bf_final,bf_bioimpedancia,bf_calculado,bf_formula,cintura,ombros,biceps_d"
        ).eq("user_id", get_uid()).order("data", desc=True).execute()
        if res_h.data:
            df_med = pd.DataFrame(res_h.data)
            st.dataframe(df_med, use_container_width=True, hide_index=True)
            # Delete de medida semanal
            if len(df_med) > 0:
                del_id = st.selectbox(
                    "Deletar medida semanal por data:",
                    options=["—"] + list(df_med["data"].astype(str)),
                    key="del_med_sel"
                )
                if del_id != "—":
                    row_d = df_med[df_med["data"].astype(str) == del_id].iloc[0]
                    if st.button(f"🗑️ Deletar medida de {del_id}", key="btn_del_med"):
                        deletar_medida_semanal(str(row_d["id"]))
                        st.rerun()
        else:
            st.info("Nenhuma medida semanal registrada ainda.")
    except Exception as e:
        st.warning(f"Erro ao carregar histórico de medidas: {e}")


def tab_avaliacao_semanal(atleta, df_historico: pd.DataFrame, fase: str):
    st.header("📊 Avaliação Semanal & Ajuste de Protocolo")

    metas = calcular_metas_semana(atleta)

    # ── Metas da semana ───────────────────────────────────────────────────────
    st.subheader(f"🎯 Metas desta Semana — {metas['fase']}")
    st.caption(f"*{metas.get('referencia','')}*")
    st.info(metas.get("descricao",""))

    if metas["fase"] == "Bulking":
        c1,c2,c3,c4 = st.columns(4)
        c1.metric("Ganho Peso Alvo", f"+{metas['ganho_peso_alvo']}kg")
        c2.metric("Ganho LBM Alvo", f"+{metas['ganho_lbm_alvo']}kg")
        c3.metric("Ganho FM Máx", f"+{metas['ganho_fm_max']}kg")
        c4.metric("BF% Máximo", f"{metas['bf_max']}%")
    elif metas["fase"] == "Cutting":
        c1,c2,c3 = st.columns(3)
        c1.metric("Perda Peso Alvo", f"-{metas['perda_peso_alvo']}kg")
        c2.metric("Intervalo Seguro", f"-{metas['perda_peso_min']} a -{metas['perda_peso_max']}kg")
        c3.metric("Perda LBM Máx", f"-{metas['perda_lbm_max']}kg")

    st.divider()

    # ── Avaliação dos resultados ──────────────────────────────────────────────
    st.subheader("🔍 Resultado da Última Semana")
    resultado = avaliar_resultados_semana(df_historico, metas, fase)

    if resultado["status"] == "insuficiente":
        st.warning(resultado.get("msg","Dados insuficientes."))
        st.caption("Registre dados diários por pelo menos 7 dias para ativar a avaliação automática.")
        return

    # Métricas do período
    c1,c2,c3,c4 = st.columns(4)
    delta_p = resultado["delta_peso"]
    delta_l = resultado["delta_lbm"]
    delta_f = resultado["delta_fm"]
    delta_b = resultado["delta_bf"]
    c1.metric("Δ Peso",  f"{delta_p:+.2f}kg", delta_color="normal")
    c2.metric("Δ LBM",   f"{delta_l:+.2f}kg", delta_color="normal")
    c3.metric("Δ FM",    f"{delta_f:+.2f}kg",  delta_color="inverse")
    c4.metric("Δ BF%",   f"{delta_b:+.2f}%",   delta_color="inverse")

    st.divider()

    # ── CONFLITO MULTI-OBJETIVO ───────────────────────────────────────────────
    if resultado["status"] == "conflito" and resultado["conflitos"]:
        conflito = resultado["conflitos"][0]
        st.error(conflito["descricao"])
        st.markdown("**Escolha sua prioridade para recalcular o protocolo:**")

        opcoes = conflito["opcoes"]
        escolha = st.radio(
            "Prioridade",
            options=[o["label"] for o in opcoes],
            key="conflito_prioridade",
        )
        idx = [o["label"] for o in opcoes].index(escolha)
        op_sel = opcoes[idx]
        st.info(f"**{op_sel['label']}:** {op_sel['descricao']}")

        delta_cal = op_sel["delta_calorias"]
        if delta_cal > 0:
            st.success(f"**Ajuste:** +{delta_cal}kcal/dia nas calorias totais do plano semanal.")
        elif delta_cal < 0:
            st.warning(f"**Ajuste:** {delta_cal}kcal/dia nas calorias totais do plano semanal.")
        else:
            st.info("Manter protocolo atual.")

    # ── Ajustes recomendados (sem conflito) ───────────────────────────────────
    elif resultado["status"] == "on_track":
        st.success("✅ **Dentro das metas!** Manter protocolo atual.")

    elif resultado["ajustes"]:
        st.subheader("⚡ Ajustes Recomendados")
        for aj in resultado["ajustes"]:
            pri_emoji = "🔴" if aj.get("prioridade",2)==0 else ("🟡" if aj.get("prioridade",2)==1 else "🔵")
            delta = aj["delta_calorias"]
            sinal = f"+{delta}" if delta > 0 else str(delta)
            st.markdown(
                f"{pri_emoji} **{aj['objetivo']}** — {aj['problema']}  \n"
                f"→ **Ação:** {aj['acao']} (**{sinal}kcal/dia**)"
            )

    st.divider()
    st.subheader("📖 Base Científica — Otimização Multi-Objetivo")

    with st.expander("Taxa de Ganho Ótima no Bulking — Iraki et al., 2019", expanded=True):
        anos = atleta.anos_treino
        st.markdown(f"""
**Nível atual: {'Novato' if anos<=2 else ('Intermediário' if anos<=4 else 'Avançado')} ({anos} anos)**

| Nível | Taxa/semana | Razão |
|---|---|---|
| Novato (≤2 anos) | 0.5% peso corporal | Alta capacidade de síntese proteica |
| Intermediário (2-4 anos) | 0.35% peso corporal | Capacidade moderada |
| Avançado (5+ anos) | 0.25% peso corporal | Próximo do potencial genético |

Taxas mais rápidas não aumentam ganho de LBM proporcionalmente,
apenas aumentam o ganho de gordura. *(Helms et al., 2022 — PMC10620361)*

**Composição ideal do ganho semanal:**
- 60-65% LBM (músculo, glicogênio, água intracelular)
- 35-40% FM máximo
        """)

    with st.expander("Taxa de Perda Ótima no Cutting — Helms et al., 2014"):
        st.markdown(f"""
**0.5–1.0% do peso corporal por semana** maximiza perda de gordura
enquanto preserva massa magra. *(Helms et al., 2014 — PubMed 24864135)*

**Abaixo de 0.5%/sem:** déficit insuficiente — ampliar.
**Acima de 1.0%/sem:** risco de perda de LBM — reduzir.

**Proteína mínima no cutting:** 3.1g/kg LBM para preservar LBM máxima.
*(Helms et al., 2014)*
        """)

    with st.expander("Conflito Multi-Objetivo — Por que acontece?"):
        st.markdown("""
Em certas situações, objetivos diferentes apontam para direções opostas nas calorias:

**Bulking:** Ganhar peso insuficientemente (quer +calorias) enquanto o BF% sobe rápido
(quer -calorias) cria um paradoxo. Isso geralmente indica:
- Partição calórica ruim (alta gordura corporal inicial)
- Treino insuficiente para absorver o superávit em síntese proteica
- Necessidade de mini-cut antes de continuar

**Cutting:** Perder peso lentamente (quer mais déficit) enquanto perde LBM excessivamente
(quer menos déficit) indica:
- Proteína insuficiente
- Déficit muito agressivo para o nível atual de BF%
- Priorizar: perda de gordura (aceita LBM) ou preservação de LBM (perda mais lenta)

O sistema detecta automaticamente e apresenta as opções — a decisão é do atleta.
        """)


def tab_referencias():
    st.header("📚 Base Científica Completa")
    st.caption("30+ referências peer-reviewed utilizadas nas recomendações do sistema.")
    modulos  = ["Periodização","Nutrição","Treino","Recuperação","Suplementação"]
    emojis_m = {"Periodização":"🟣","Nutrição":"🔴","Treino":"🟢","Recuperação":"🟡","Suplementação":"🔵"}
    for i, tab in enumerate(st.tabs([f"{emojis_m[m]} {m}" for m in modulos])):
        with tab:
            _render_refs(modulos[i], card=True)
    st.divider()
    st.caption("⚕️ Ferramenta educacional — não substitui avaliação de profissionais de saúde.")

# ─────────────────────────────────────────────────────────────────────────────
# APP PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

def render_app():
    # Carregar perfil
    if "perfil" not in st.session_state:
        st.session_state["perfil"] = carregar_perfil()
    perfil = st.session_state["perfil"]
    if not perfil:
        render_onboarding()
        return

    # Carregar dados
    df_historico = carregar_registros()

    # Carregar última medida semanal (peso, BF%, etc.)
    medida = carregar_ultima_medida_semanal()
    # Peso e BF% vêm das medidas semanais; fallback para histórico diário
    peso_atual = float(medida.get("peso") or 0)
    bf_atual   = float(medida.get("bf_final") or medida.get("bf_calculado") or
                       medida.get("bf_bioimpedancia") or 0)
    if peso_atual == 0 and not df_historico.empty:
        try: peso_atual = float(df_historico.sort_values("Data").iloc[-1]["Peso"])
        except: peso_atual = 85.0
    if bf_atual == 0 and not df_historico.empty:
        try: bf_atual = float(df_historico.sort_values("Data").iloc[-1]["BF_Atual"])
        except: bf_atual = 12.0
    if peso_atual == 0: peso_atual = 85.0
    if bf_atual   == 0: bf_atual   = 12.0

    # Sidebar (somente dados diários)
    p = render_sidebar(perfil)
    # Injetar peso e BF das medidas semanais no dict p
    p["peso_at"] = peso_atual
    p["bf_at"]   = bf_atual

    # ── Botões CRUD diário na sidebar ─────────────────────────────────────────
    st.sidebar.divider()
    sel = st.session_state.get("linha_selecionada")

    def _build_registro_payload(data_str: str, fase_s: str, df_h: pd.DataFrame,
                                  peso: float, bf: float) -> dict:
        """Monta o payload do registro diário usando peso/BF das medidas semanais."""
        atleta_t = AtletaMetrics(
            categoria_alvo=p["categoria"], peso=peso, bf_atual=bf,
            bf_alvo=p["bf_alvo"], idade=p["idade"], vfc_base=p["vfc_base"],
            vfc_atual=p["vfc_at"], sleep_score=p["sleep_sc"], recovery_time=p["rec_time"],
            fc_repouso=p["fc_rep"], carga_treino=p["carga_tr"], fase_sugerida=fase_s,
            uso_peds=p["uso_peds"], estagnado_dias=0, data_competicao=p["data_comp"],
            anos_treino=p.get("anos_treino",5),
        )
        df_d, _, _ = calcular_macros_semana(atleta_t, df_h, {})
        try:
            wd = datetime.strptime(data_str, "%Y-%m-%d").weekday()
        except:
            wd = 0
        dh = df_d.iloc[wd]
        return {
            "Data": data_str, "Peso": peso, "BF_Atual": bf,
            "Carga_Treino": p["carga_tr"], "VFC_Atual": p["vfc_at"],
            "Sleep_Score": p["sleep_sc"], "Recovery_Time": p["rec_time"],
            "FC_Repouso": p["fc_rep"], "Fase_Historica": fase_s,
            "Estrategia_Dieta": dh["Estratégia"], "Calorias": dh["Calorias"],
            "Carboidratos": dh["Carb(g)"], "Proteinas": dh["Prot(g)"], "Gorduras": dh["Gord(g)"],
        }

    if sel:
        # BUG FIX: usar a data diretamente de linha_selecionada, não do widget
        data_selecionada = str(sel["Data"])
        cb1, cb2 = st.sidebar.columns(2)
        if cb1.button("✏️ Atualizar", type="primary", use_container_width=True):
            fase_t, _, _ = sugerir_fase_e_timeline(
                date.today(), p["data_comp"], p["bf_at"], p["sexo"], df_historico)
            payload = _build_registro_payload(data_selecionada, fase_t, df_historico,
                                               peso_atual, bf_atual)
            salvar_registro(payload)
            st.session_state["linha_selecionada"] = None
            st.rerun()
        if cb2.button("🗑️ Deletar", use_container_width=True):
            # BUG FIX: deletar pela data de linha_selecionada, não pelo widget
            deletar_registro(data_selecionada)
            st.session_state["linha_selecionada"] = None
            st.rerun()
    else:
        if st.sidebar.button("💾 Salvar Registro do Dia", type="primary", use_container_width=True):
            fase_t, _, _ = sugerir_fase_e_timeline(
                date.today(), p["data_comp"], p["bf_at"], p["sexo"], df_historico)
            payload = _build_registro_payload(
                str(p["data_reg"]), fase_t, df_historico, peso_atual, bf_atual)
            salvar_registro(payload)
            st.rerun()

    # ── Lógica central ────────────────────────────────────────────────────────
    fase, df_timeline, flags = sugerir_fase_e_timeline(
        date.today(), p["data_comp"], p["bf_at"], p["sexo"], df_historico)

    atleta = AtletaMetrics(
        categoria_alvo=p["categoria"], peso=p["peso_at"], bf_atual=p["bf_at"],
        bf_alvo=p["bf_alvo"], idade=p["idade"], vfc_base=p["vfc_base"],
        vfc_atual=p["vfc_at"], sleep_score=p["sleep_sc"], recovery_time=p["rec_time"],
        fc_repouso=p["fc_rep"], carga_treino=p["carga_tr"], fase_sugerida=fase,
        uso_peds=p["uso_peds"], estagnado_dias=0, data_competicao=p["data_comp"],
        anos_treino=p.get("anos_treino", 5),
    )
    df_dieta, motivo_dieta, alertas = calcular_macros_semana(atleta, df_historico, flags)
    dieta_hoje = df_dieta.iloc[p["data_reg"].weekday()]

    # ── Navegação ─────────────────────────────────────────────────────────────
    st.title("🧬 Pro Coach IA")

    tabs = st.tabs([
        "🏠 Dashboard",
        "🗓️ Periodização",
        "🍽️ Nutrição",
        "🏋️ Treino",
        "🎯 Recuperação",
        "📁 Registros",
        "📊 Avaliação Semanal",
        "💊 Suplementação",
        "📈 Evolução",
        "📚 Referências",
    ])

    with tabs[0]: tab_dashboard(p, atleta, flags, fase, df_historico, df_timeline, dieta_hoje, df_dieta)
    with tabs[1]: tab_periodizacao(fase, df_timeline, flags, p, atleta, df_historico)
    with tabs[2]: tab_nutricao(fase, atleta, df_historico, flags, df_dieta, motivo_dieta, alertas, dieta_hoje, p)
    with tabs[3]: tab_treino(fase, atleta, df_historico)
    with tabs[4]: tab_recuperacao(atleta, df_historico, p)
    with tabs[5]: tab_registros(p, atleta, perfil, df_historico)
    with tabs[6]: tab_avaliacao_semanal(atleta, df_historico, fase)
    with tabs[7]: tab_suplementacao(atleta)
    with tabs[8]: tab_evolucao(df_historico)
    with tabs[9]: tab_referencias()


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if not sessao_ativa():
    render_tela_auth()
else:
    render_app()