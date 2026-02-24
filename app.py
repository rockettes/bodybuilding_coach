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
    initial_sidebar_state="collapsed",
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
# CRUD — medidas_atleta (tabela unificada de todos os registros)
# ─────────────────────────────────────────────────────────────────────────────

def carregar_todos_registros() -> pd.DataFrame:
    """Carrega todos os registros de medidas_atleta do usuário."""
    try:
        res = _client().table("medidas_atleta").select("*") \
            .eq("user_id", get_uid()).order("data", desc=True).execute()
        return pd.DataFrame(res.data) if res.data else pd.DataFrame()
    except Exception as e:
        st.warning(f"Erro ao carregar registros: {e}")
        return pd.DataFrame()


def carregar_ultimo_registro() -> dict:
    """Retorna o registro mais recente (com cache de sessão)."""
    if "ultimo_registro_cache" in st.session_state:
        return st.session_state["ultimo_registro_cache"]
    try:
        res = _client().table("medidas_atleta").select("*") \
            .eq("user_id", get_uid()).order("data", desc=True).limit(1).execute()
        r = res.data[0] if res.data else {}
        st.session_state["ultimo_registro_cache"] = r
        return r
    except:
        return {}


def salvar_novo_registro(dados: dict) -> None:
    """Insere novo registro em medidas_atleta."""
    try:
        payload = _clean({**dados, "user_id": get_uid()})
        _client().table("medidas_atleta").insert(payload).execute()
        for k in ["ultimo_registro_cache","ultima_medida"]:
            st.session_state.pop(k, None)
        st.toast("✅ Registro salvo!", icon="💾")
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")


def atualizar_registro(record_id: str, dados: dict) -> None:
    """Atualiza registro existente em medidas_atleta pelo ID."""
    try:
        payload = _clean(dados)
        payload.pop("user_id", None)
        payload.pop("id", None)
        _client().table("medidas_atleta").update(payload) \
            .eq("id", record_id).eq("user_id", get_uid()).execute()
        for k in ["ultimo_registro_cache","ultima_medida"]:
            st.session_state.pop(k, None)
        st.toast("✅ Registro atualizado!", icon="✏️")
    except Exception as e:
        st.error(f"Erro ao atualizar: {e}")


def deletar_registro_unificado(record_id: str) -> None:
    """Deleta registro de medidas_atleta pelo ID."""
    try:
        _client().table("medidas_atleta").delete() \
            .eq("id", record_id).eq("user_id", get_uid()).execute()
        for k in ["ultimo_registro_cache","ultima_medida"]:
            st.session_state.pop(k, None)
        st.toast("🗑️ Registro deletado.")
    except Exception as e:
        st.error(f"Erro ao deletar: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — TREINO MANUAL
# ─────────────────────────────────────────────────────────────────────────────

def carregar_treino_manual() -> pd.DataFrame:
    try:
        r = _client().table("treino_manual") \
            .select("*").eq("user_id", get_uid()) \
            .order("created_at", desc=False).execute()
        if r.data:
            df = pd.DataFrame(r.data)
            cols = ["id","treino","exercicio","series","reps","rir","descanso_s","musculo","notas"]
            for c in cols:
                if c not in df.columns:
                    df[c] = None
            return df[cols]
        return pd.DataFrame(columns=["id","treino","exercicio","series","reps","rir","descanso_s","musculo","notas"])
    except Exception as e:
        st.error(f"Erro ao carregar treino manual: {e}")
        return pd.DataFrame(columns=["id","treino","exercicio","series","reps","rir","descanso_s","musculo","notas"])

def salvar_treino_manual(df: pd.DataFrame) -> None:
    """Substitui todo o treino manual do atleta (delete + insert)."""
    uid = get_uid()
    try:
        _client().table("treino_manual").delete().eq("user_id", uid).execute()
        rows = df.copy()
        rows["user_id"] = uid
        # Renomear colunas do treino automático para snake_case do DB
        col_map = {
            "Treino":"treino","Exercício":"exercicio","Séries":"series",
            "Reps":"reps","RIR":"rir","Descanso(s)":"descanso_s","Músculo":"musculo","Notas":"notas",
        }
        rows = rows.rename(columns=col_map)
        db_cols = ["user_id","treino","exercicio","series","reps","rir","descanso_s","musculo","notas"]
        rows = rows[[c for c in db_cols if c in rows.columns]]
        rows = rows.where(pd.notnull(rows), None)
        data = rows.to_dict(orient="records")
        if data:
            _client().table("treino_manual").insert(data).execute()
        st.toast("✅ Treino manual salvo.")
        st.session_state.pop("treino_manual_cache", None)
    except Exception as e:
        st.error(f"Erro ao salvar treino manual: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — PERIODIZAÇÃO MANUAL
# ─────────────────────────────────────────────────────────────────────────────

def carregar_periodizacao_manual() -> pd.DataFrame:
    try:
        r = _client().table("periodizacao_manual") \
            .select("*").eq("user_id", get_uid()) \
            .order("inicio", desc=False).execute()
        if r.data:
            df = pd.DataFrame(r.data)
            for c in ["id","fase","inicio","fim","objetivo","notas"]:
                if c not in df.columns:
                    df[c] = None
            return df[["id","fase","inicio","fim","objetivo","notas"]]
        return pd.DataFrame(columns=["id","fase","inicio","fim","objetivo","notas"])
    except Exception as e:
        st.error(f"Erro ao carregar periodização manual: {e}")
        return pd.DataFrame(columns=["id","fase","inicio","fim","objetivo","notas"])

def salvar_periodizacao_manual(df: pd.DataFrame) -> None:
    uid = get_uid()
    try:
        _client().table("periodizacao_manual").delete().eq("user_id", uid).execute()
        rows = df.copy()
        rows["user_id"] = uid
        col_map = {"Fase":"fase","Inicio":"inicio","Fim":"fim","Objetivo":"objetivo","Notas":"notas"}
        rows = rows.rename(columns=col_map)
        for c in ["inicio","fim"]:
            if c in rows.columns:
                rows[c] = pd.to_datetime(rows[c], errors="coerce").dt.strftime("%Y-%m-%d")
        db_cols = ["user_id","fase","inicio","fim","objetivo","notas"]
        rows = rows[[c for c in db_cols if c in rows.columns]]
        rows = rows.where(pd.notnull(rows), None)
        data = [r for r in rows.to_dict(orient="records") if r.get("fase")]
        if data:
            _client().table("periodizacao_manual").insert(data).execute()
        st.toast("✅ Periodização manual salva.")
        st.session_state.pop("periodizacao_manual_cache", None)
    except Exception as e:
        st.error(f"Erro ao salvar periodização manual: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — DIETA MANUAL
# ─────────────────────────────────────────────────────────────────────────────

def carregar_dieta_manual() -> pd.DataFrame:
    try:
        r = _client().table("dieta_manual") \
            .select("*").eq("user_id", get_uid()) \
            .order("created_at", desc=False).execute()
        if r.data:
            df = pd.DataFrame(r.data)
            for c in ["id","data_ref","refeicao","alimento","qtd","calorias","proteina","carboidrato","gordura","notas"]:
                if c not in df.columns:
                    df[c] = None
            return df[["id","data_ref","refeicao","alimento","qtd","calorias","proteina","carboidrato","gordura","notas"]]
        return pd.DataFrame(columns=["id","data_ref","refeicao","alimento","qtd","calorias","proteina","carboidrato","gordura","notas"])
    except Exception as e:
        st.error(f"Erro ao carregar dieta manual: {e}")
        return pd.DataFrame(columns=["id","data_ref","refeicao","alimento","qtd","calorias","proteina","carboidrato","gordura","notas"])

def salvar_dieta_manual(df: pd.DataFrame, data_ref: str) -> None:
    uid = get_uid()
    try:
        _client().table("dieta_manual").delete() \
            .eq("user_id", uid).eq("data_ref", data_ref).execute()
        rows = df.copy()
        rows["user_id"] = uid
        rows["data_ref"] = data_ref
        col_map = {
            "Refeição":"refeicao","Alimento":"alimento","Qtd":"qtd",
            "Calorias":"calorias","Proteína(g)":"proteina",
            "Carb(g)":"carboidrato","Gordura(g)":"gordura","Notas":"notas",
        }
        rows = rows.rename(columns=col_map)
        db_cols = ["user_id","data_ref","refeicao","alimento","qtd","calorias","proteina","carboidrato","gordura","notas"]
        rows = rows[[c for c in db_cols if c in rows.columns]]
        rows = rows.where(pd.notnull(rows), None)
        data = [r for r in rows.to_dict(orient="records") if r.get("refeicao") or r.get("alimento")]
        if data:
            _client().table("dieta_manual").insert(data).execute()
        st.toast("✅ Dieta manual salva.")
        st.session_state.pop("dieta_manual_cache", None)
    except Exception as e:
        st.error(f"Erro ao salvar dieta manual: {e}")


# Compatibilidade retroativa (usadas em partes não refatoradas ainda)
def carregar_registros() -> pd.DataFrame:
    df = carregar_todos_registros()
    if df.empty:
        return pd.DataFrame()
    rename = {
        "data":"Data","peso":"Peso","bf_final":"BF_Atual","carga_treino":"Carga_Treino",
        "vfc_noturna":"VFC_Atual","sleep_score":"Sleep_Score","recovery_time":"Recovery_Time",
        "fc_repouso":"FC_Repouso",
    }
    return df.rename(columns={k:v for k,v in rename.items() if k in df.columns})

def carregar_ultima_medida_semanal() -> dict:
    return carregar_ultimo_registro()


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
# TOPBAR — barra superior mínima (sem sidebar)
# ─────────────────────────────────────────────────────────────────────────────

def render_topbar(perfil: dict) -> None:
    """Barra superior: título + nome do usuário + botão de logout."""
    col_t, col_u = st.columns([5, 1])
    with col_t:
        st.markdown(f"## 🧬 Pro Coach IA")
    with col_u:
        nome = perfil.get("nome","Atleta").split()[0]
        st.markdown(f"**👤 {nome}**")
        if st.button("Sair", use_container_width=True, key="topbar_logout"):
            fazer_logout()
    st.divider()





# ─────────────────────────────────────────────────────────────────────────────
# ABAS DO APP
# ─────────────────────────────────────────────────────────────────────────────

def tab_dashboard(p, atleta, flags, fase, df_hist, df_timeline, dieta_hoje, df_dieta):
    st.header("🏠 Dashboard do Dia")

    # ── Próxima fase a partir da timeline ─────────────────────────────────────
    proxima_fase = None
    dias_proxima = None
    if not df_timeline.empty:
        projs = df_timeline[df_timeline["Fase"].str.startswith("Projeção:")].copy()
        projs["Inicio"] = pd.to_datetime(projs["Inicio"], errors="coerce")
        futuras = projs[projs["Inicio"] > pd.Timestamp(date.today())]
        if not futuras.empty:
            prox = futuras.sort_values("Inicio").iloc[0]
            proxima_fase = prox["Fase"].replace("Projeção: ","")
            dias_proxima = (prox["Inicio"].date() - date.today()).days

    # ── Métricas de cabeçalho ─────────────────────────────────────────────────
    dias_show = max(0, (p['data_comp'] - date.today()).days)
    taxa = f"{flags['taxa_perda_peso']:.2f}%/sem" if flags.get("taxa_perda_peso") else "—"
    peso_txt = f"{p['peso_at']} kg" if p['peso_at'] else "—"
    bf_txt   = f"{p['bf_at']}%"    if p['bf_at']   else "—"

    cols_header = st.columns(6)
    cols_header[0].metric("🏁 Fase Atual",      fase)
    cols_header[1].metric("📅 Dias p/ Show",    f"{dias_show}d")
    cols_header[2].metric("⏭ Próxima Fase",     proxima_fase or "—",
                          delta=f"em {dias_proxima}d" if dias_proxima else None)
    cols_header[3].metric("📉 Taxa de Perda",   taxa)
    cols_header[4].metric("⚖️ Peso Atual",       peso_txt)
    cols_header[5].metric("🔬 BF% Atual",        bf_txt)

    if flags.get("plato_metabolico"):
        st.error("🚨 **PLATÔ METABÓLICO** — Taxa < 0.5%/sem por 2 semanas. *(Peos et al., 2019)*")

    st.divider()

    # ── Linha: Recuperação | Comparativo Atual vs Objetivo ───────────────────
    col_rec, col_obj = st.columns([1, 1])

    with col_rec:
        st.subheader("🎯 Status de Recuperação")
        ultimo = carregar_ultimo_registro()
        tem_dados_rec = (
            float(ultimo.get("vfc_noturna")   or 0) > 0 or
            float(ultimo.get("sleep_score")   or 0) > 0 or
            float(ultimo.get("recovery_time") or 0) > 0
        )
        if tem_dados_rec:
            (status_dia, acao_dia, motivo_dia, painel,
             acwr_val, acwr_status, cv_val, cv_status) = prescrever_treino_do_dia(atleta, df_hist)
            fn = st.error if "Severa" in status_dia else (st.warning if "Incompleta" in status_dia else st.success)
            fn(f"**{status_dia}**")
            st.info(f"**AÇÃO:** {acao_dia}")
            st.caption(f"*{motivo_dia}*")
        else:
            st.info("📊 Registre VFC Noturna, Sleep Score ou Recovery Time na aba **📁 Registros** para ver o status de recuperação.")

        st.divider()
        st.subheader(f"🍽️ Alvo Nutricional — {dieta_hoje['Estratégia']}")
        mc1,mc2,mc3,mc4 = st.columns(4)
        mc1.metric("Calorias",  f"{dieta_hoje['Calorias']} kcal")
        mc2.metric("Proteína",  f"{dieta_hoje['Prot(g)']}g")
        mc3.metric("Carb",      f"{dieta_hoje['Carb(g)']}g")
        mc4.metric("Gordura",   f"{dieta_hoje['Gord(g)']}g")

    with col_obj:
        st.subheader("🎯 Atual vs Objetivo")

        peso_atual = p.get("peso_at") or 0
        bf_atual_v = p.get("bf_at") or 0
        bf_alvo    = p.get("bf_alvo", 5.0)

        # Medidas do último registro
        ult        = carregar_ultimo_registro()
        cintura_at = float(ult.get("cintura") or 0) or None
        ombros_at  = float(ult.get("ombros")  or 0) or None
        coxa_at    = float(ult.get("coxa_d")  or 0) or None

        from calculos_fisio import PROPORCOES_CATEGORIA, PHI
        prop_cat = PROPORCOES_CATEGORIA.get(p["categoria"], {})
        phi_cat  = prop_cat.get("ombro_cintura_ratio_alvo", PHI)
        alt      = float(p.get("altura") or 178.0)

        # ── Objetivos: perfil manual > calculado automaticamente ──────────────
        # ORDEM IMPORTA: cintura_alvo deve ser calculada antes de ombros_alvo

        # 1. Cintura alvo: manual > ombros_at/φ > altura×pct
        cintura_alvo = p.get("cintura_alvo_pf")
        if not cintura_alvo and ombros_at:
            cintura_alvo = round(ombros_at / phi_cat, 1)
        if not cintura_alvo:
            cintura_alvo = round(alt * prop_cat.get("cintura_max_pct_altura", 0.44), 1)

        # 2. Ombros alvo: manual > cintura_ALVO×φ (não cintura atual!)
        ombros_alvo = p.get("ombros_alvo_pf")
        if not ombros_alvo and cintura_alvo:
            ombros_alvo = round(cintura_alvo * phi_cat, 1)

        # 3. Peso alvo: manual > FFM/(1-bf_alvo%)
        peso_alvo = p.get("peso_alvo_pf")
        if not peso_alvo and peso_atual and bf_atual_v:
            ffm = peso_atual * (1 - bf_atual_v / 100)
            peso_alvo = round(ffm / (1 - bf_alvo / 100), 1)

        # 4. Coxa alvo: manual > referência pela altura
        coxa_alvo = p.get("coxa_alvo_pf")
        if not coxa_alvo:
            coxa_pct  = 0.55 if "Open" in p.get("categoria","") else 0.52
            coxa_alvo = round(alt * coxa_pct, 1)

        tem_manual = any([p.get("peso_alvo_pf"), p.get("cintura_alvo_pf"),
                          p.get("ombros_alvo_pf"), p.get("coxa_alvo_pf")])
        fonte_obj = "📌 manuais (Perfil)" if tem_manual else "📐 calculados (Razão Áurea + BF% alvo)"

        # Montar tabela comparativa
        rows = []
        def _row(nome, atual, alvo, unidade=""):
            atual_s = f"{atual:.1f}{unidade}" if atual else "—"
            alvo_s  = f"{alvo:.1f}{unidade}"  if alvo  else "—"
            if atual and alvo:
                delta   = atual - alvo
                delta_s = f"{delta:+.1f}{unidade}"
                tol     = 0.5 if "%" in unidade else 1.0
                tol_med = 2.0 if "%" in unidade else 5.0
                status  = "✅" if abs(delta) <= tol else ("🟡" if abs(delta) <= tol_med else "🔴")
            else:
                delta_s = "—"; status = "⬜"
            rows.append({"Variável": f"{status} {nome}", "Atual": atual_s, "Objetivo": alvo_s, "Δ": delta_s})

        _row("Peso",    peso_atual or None, peso_alvo,   unidade=" kg")
        _row("BF%",     bf_atual_v or None, bf_alvo,     unidade="%")
        _row("Cintura", cintura_at,         cintura_alvo, unidade=" cm")
        _row("Ombros",  ombros_at,          ombros_alvo,  unidade=" cm")
        _row("Coxa D",  coxa_at,            coxa_alvo,    unidade=" cm")

        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            st.caption(f"Objetivos {fonte_obj}. Configure manualmente na aba **👤 Perfil**.")
        else:
            st.info("Registre medidas e configure o BF% alvo no **Perfil** para ver o comparativo.")

        # ── Proporções ──────────────────────────────────────────────────────────
        st.divider()
        st.subheader("📐 Proporções Estéticas")
        medidas_d = {
            "cintura":  float(ult.get("cintura")  or 0),
            "ombros":   float(ult.get("ombros")   or 0),
            "peito":    float(ult.get("peito")    or 0),
            "quadril":  float(ult.get("quadril")  or 0),
            "biceps_d": float(ult.get("biceps_d") or 0),
            "coxa_d":   float(ult.get("coxa_d")   or 0),
        }
        altura_cm = float(p.get("altura") or 178.0)
        if any(v > 0 for v in medidas_d.values()):
            props = avaliar_proporcoes(p["categoria"], medidas_d, altura_cm)
            if "ombro_cintura" in props:
                r = props["ombro_cintura"]
                prog = min(r["atual"] / r["alvo"], 1.0) if r.get("alvo",0) > 0 else 0
                st.progress(prog, text=f"Ombro/Cintura: {r['atual']:.3f} / φ {r['alvo']} — {r['status']}")
            for key, dados in props.items():
                if key == "ombro_cintura": continue
                alvo = dados.get("alvo") or dados.get("alvo_max","—")
                st.write(f"{dados['status']} **{key.replace('_',' ').title()}** — Atual: `{dados.get('atual','—')}` | Alvo: `{alvo}`")
        else:
            st.info("Registre circunferências na aba **📁 Registros** para ver as proporções.")



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

    # ══════════════════════════════════════════════════════════════════════
    # PERIODIZAÇÃO MANUAL — adicional à automática
    # ══════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("📅 Periodização Manual")
    st.caption(
        "Defina suas próprias fases aqui. "
        "Não substitui o cálculo automático — ambos são exibidos. "
        "Edite diretamente nas células ou importe um CSV."
    )

    _COLUNAS_PERIOD = ["Fase", "Inicio", "Fim", "Objetivo", "Notas"]

    # Carregar do Supabase na primeira vez
    if "periodizacao_manual_df" not in st.session_state:
        raw_p = carregar_periodizacao_manual()
        if not raw_p.empty:
            col_map_p = {"fase":"Fase","inicio":"Inicio","fim":"Fim","objetivo":"Objetivo","notas":"Notas"}
            raw_p = raw_p.drop(columns=["id"], errors="ignore").rename(columns=col_map_p)
            st.session_state["periodizacao_manual_df"] = raw_p[[c for c in _COLUNAS_PERIOD if c in raw_p.columns]]
        else:
            st.session_state["periodizacao_manual_df"] = pd.DataFrame(columns=_COLUNAS_PERIOD)

    # ── Import CSV de periodização ────────────────────────────────────────
    with st.expander("📂 Importar periodização por CSV"):
        st.caption(
            f"Colunas: `{' | '.join(_COLUNAS_PERIOD)}`  \n"
            "Datas no formato `AAAA-MM-DD` (ex: `2025-03-01`)"
        )
        _ph = st.checkbox(
            "O arquivo CSV possui cabeçalho (primeira linha = nomes das colunas)",
            value=True, key="period_csv_header",
        )
        _pf = st.file_uploader("Selecione o arquivo .csv", type=["csv"], key="period_csv_upload")
        if _pf is not None:
            try:
                _dfp = pd.read_csv(_pf, sep=None, engine="python", header=0 if _ph else None)
                if not _ph:
                    n = min(len(_COLUNAS_PERIOD), len(_dfp.columns))
                    _dfp.columns = list(_COLUNAS_PERIOD[:n]) + list(_dfp.columns[n:])
                _cols_p = [c for c in _COLUNAS_PERIOD if c in _dfp.columns]
                st.session_state["periodizacao_manual_df"] = _dfp[_cols_p].copy()
                st.success(f"✅ {len(_dfp)} fases importadas.")
            except Exception as _ep:
                st.error(f"Erro ao ler CSV: {_ep}")

    # ── Editor de periodização manual ─────────────────────────────────────
    st.markdown("**✏️ Fases manuais (clique nas células para editar):**")
    _dfp_edit = st.data_editor(
        st.session_state["periodizacao_manual_df"],
        num_rows="dynamic",
        use_container_width=True,
        key="periodizacao_manual_editor",
        column_config={
            "Fase":     st.column_config.TextColumn("Fase"),
            "Inicio":   st.column_config.DateColumn("Início",  format="YYYY-MM-DD"),
            "Fim":      st.column_config.DateColumn("Fim",     format="YYYY-MM-DD"),
            "Objetivo": st.column_config.TextColumn("Objetivo"),
            "Notas":    st.column_config.TextColumn("Notas"),
        },
    )
    st.session_state["periodizacao_manual_df"] = _dfp_edit

    # ── Botões Salvar / Limpar ────────────────────────────────────────────
    _pp1, _pp2, _pp3 = st.columns([2, 1, 1])
    if _pp1.button("💾 Salvar periodização manual no banco", key="btn_salvar_period_manual",
                   type="primary", use_container_width=True):
        salvar_periodizacao_manual(_dfp_edit)
    if _pp3.button("🗑️ Limpar", key="btn_limpar_period_manual", use_container_width=True):
        st.session_state["periodizacao_manual_df"] = pd.DataFrame(columns=_COLUNAS_PERIOD)
        salvar_periodizacao_manual(pd.DataFrame(columns=_COLUNAS_PERIOD))
        st.rerun()

    # ── Timeline manual (se houver dados válidos) ─────────────────────────
    _dfp_valid = _dfp_edit.dropna(subset=["Fase","Inicio","Fim"])
    if not _dfp_valid.empty:
        try:
            _dfp_valid = _dfp_valid.copy()
            _dfp_valid["Inicio"] = pd.to_datetime(_dfp_valid["Inicio"])
            _dfp_valid["Fim"]    = pd.to_datetime(_dfp_valid["Fim"])
            st.markdown("**📊 Timeline manual:**")
            _fig_m = px.timeline(
                _dfp_valid, x_start="Inicio", x_end="Fim", y="Fase",
                color="Fase", color_discrete_sequence=px.colors.qualitative.Set2,
                title="Periodização Manual",
            )
            _fig_m.add_vline(x=datetime.today().strftime("%Y-%m-%d"),
                             line_width=2, line_dash="dash", line_color="crimson")
            _fig_m.add_annotation(x=datetime.today().strftime("%Y-%m-%d"), y=1.05, yref="paper",
                text="HOJE", showarrow=False, font=dict(color="crimson", size=12),
                bgcolor="rgba(255,255,255,0.8)")
            _fig_m.update_yaxes(autorange="reversed")
            st.plotly_chart(_fig_m, use_container_width=True)
        except Exception as _ef:
            st.caption(f"⚠️ Verifique o formato das datas: {_ef}")

    # ── Export periodização ────────────────────────────────────────────────
    if not df_timeline.empty or not _dfp_edit.empty:
        _opcoes_p = ["🤖 Automática (calculada)"]
        if not _dfp_edit.empty:
            _opcoes_p += ["📅 Manual", "📋 Ambas"]
        _exp_p = st.selectbox("📥 Exportar periodização:", _opcoes_p, key="period_export_choice")
        if _exp_p == "🤖 Automática (calculada)":
            _dfpe = df_timeline; _fnp = "periodizacao_auto.csv"
        elif _exp_p == "📅 Manual":
            _dfpe = _dfp_edit; _fnp = "periodizacao_manual.csv"
        else:
            _dfpe = pd.concat(
                [df_timeline.assign(Origem="Automática"), _dfp_edit.assign(Origem="Manual")],
                ignore_index=True,
            ); _fnp = "periodizacao_completa.csv"
        st.download_button(
            f"⬇️ Baixar: {_exp_p}", data=_dfpe.to_csv(sep=";", index=False),
            file_name=_fnp, mime="text/csv", key="btn_export_period",
        )

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
    st.header("🍽️ Nutrição & Suplementação")

    # Alertas adaptativos
    for key, msg in alertas.items():
        if key == "get_base":        st.caption(f"⚙️ {msg}")
        elif "⚠️" in msg or "🔴" in msg: st.warning(msg)

    # ── Plano semanal automático ──────────────────────────────────────────
    st.subheader(f"🤖 Plano Semanal Automático — {fase}")
    st.caption(motivo_dieta)
    st.markdown(
        f"**HOJE ({dieta_hoje['Dia']}):** {dieta_hoje['Estratégia']} → "
        f"**{dieta_hoje['Calorias']} kcal** | "
        f"P: {dieta_hoje['Prot(g)']}g | C: {dieta_hoje['Carb(g)']}g | G: {dieta_hoje['Gord(g)']}g"
    )
    st.dataframe(df_dieta, use_container_width=True, hide_index=True)

    # ══════════════════════════════════════════════════════════════════════
    # DIETA MANUAL
    # ══════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("📝 Dieta Manual")
    st.caption(
        "Registre sua dieta real aqui. Não substitui o plano automático — ambos ficam visíveis. "
        "Campos: **Refeição · Alimento · Qtd** (obrigatórios) + calorias e macros opcionais."
    )

    _COLUNAS_DIETA = ["Refeição","Alimento","Qtd","Calorias","Proteína(g)","Carb(g)","Gordura(g)","Notas"]

    # Data de referência para a dieta manual
    _data_dieta_ref = st.date_input(
        "📅 Data de referência da dieta manual",
        value=date.today(),
        key="dieta_manual_data_ref",
    )
    _data_ref_str = str(_data_dieta_ref)

    # Carregar do Supabase quando a data muda
    _cache_key = f"dieta_manual_df_{_data_ref_str}"
    if _cache_key not in st.session_state:
        raw_d = carregar_dieta_manual()
        if not raw_d.empty:
            raw_d_filt = raw_d[raw_d["data_ref"] == _data_ref_str].copy() if "data_ref" in raw_d.columns else raw_d.copy()
            col_map_d = {
                "refeicao":"Refeição","alimento":"Alimento","qtd":"Qtd",
                "calorias":"Calorias","proteina":"Proteína(g)",
                "carboidrato":"Carb(g)","gordura":"Gordura(g)","notas":"Notas",
            }
            raw_d_filt = raw_d_filt.drop(columns=["id","data_ref","user_id"], errors="ignore").rename(columns=col_map_d)
            raw_d_filt = raw_d_filt[[c for c in _COLUNAS_DIETA if c in raw_d_filt.columns]]
            st.session_state[_cache_key] = raw_d_filt if not raw_d_filt.empty else pd.DataFrame(columns=_COLUNAS_DIETA)
        else:
            st.session_state[_cache_key] = pd.DataFrame(columns=_COLUNAS_DIETA)

    # ── Import CSV de dieta ───────────────────────────────────────────────
    with st.expander("📂 Importar dieta por CSV"):
        st.caption(
            f"Colunas: `{' | '.join(_COLUNAS_DIETA)}`  \n"
            "Apenas **Refeição**, **Alimento** e **Qtd** são obrigatórios. "
            "Calorias e macros são opcionais."
        )
        _dh = st.checkbox(
            "O arquivo CSV possui cabeçalho (primeira linha = nomes das colunas)",
            value=True, key="dieta_csv_header",
        )
        _df_dieta_file = st.file_uploader("Selecione o arquivo .csv", type=["csv"], key="dieta_csv_upload")
        if _df_dieta_file is not None:
            try:
                _df_dieta_csv = pd.read_csv(_df_dieta_file, sep=None, engine="python",
                                            header=0 if _dh else None)
                if not _dh:
                    n = min(len(_COLUNAS_DIETA), len(_df_dieta_csv.columns))
                    _df_dieta_csv.columns = list(_COLUNAS_DIETA[:n]) + list(_df_dieta_csv.columns[n:])
                _cols_d = [c for c in _COLUNAS_DIETA if c in _df_dieta_csv.columns]
                st.session_state[_cache_key] = _df_dieta_csv[_cols_d].copy()
                st.success(f"✅ {len(_df_dieta_csv)} linhas importadas.")
            except Exception as _ed:
                st.error(f"Erro ao ler CSV: {_ed}")

    # ── Editor dieta manual ───────────────────────────────────────────────
    st.markdown("**✏️ Editar dieta (clique nas células para editar):**")
    _df_dieta_edit = st.data_editor(
        st.session_state[_cache_key],
        num_rows="dynamic",
        use_container_width=True,
        key="dieta_manual_editor",
        column_config={
            "Refeição":    st.column_config.TextColumn("Refeição",   help="Ex: Café da manhã"),
            "Alimento":    st.column_config.TextColumn("Alimento",   help="Ex: Frango grelhado"),
            "Qtd":         st.column_config.TextColumn("Qtd",        help="Ex: 200g ou 1 unidade"),
            "Calorias":    st.column_config.NumberColumn("Calorias", min_value=0, format="%d"),
            "Proteína(g)": st.column_config.NumberColumn("Prot(g)",  min_value=0, format="%.1f"),
            "Carb(g)":     st.column_config.NumberColumn("Carb(g)",  min_value=0, format="%.1f"),
            "Gordura(g)":  st.column_config.NumberColumn("Gord(g)",  min_value=0, format="%.1f"),
            "Notas":       st.column_config.TextColumn("Notas"),
        },
    )
    st.session_state[_cache_key] = _df_dieta_edit

    # ── Totais automáticos ────────────────────────────────────────────────
    _cols_num = ["Calorias","Proteína(g)","Carb(g)","Gordura(g)"]
    if not _df_dieta_edit.empty:
        _totais = {}
        for _c in _cols_num:
            if _c in _df_dieta_edit.columns:
                _totais[_c] = pd.to_numeric(_df_dieta_edit[_c], errors="coerce").sum()
        if any(v > 0 for v in _totais.values()):
            _t1, _t2, _t3, _t4 = st.columns(4)
            _t1.metric("Total kcal",    f"{_totais.get('Calorias',0):.0f}")
            _t2.metric("Proteína",      f"{_totais.get('Proteína(g)',0):.1f}g")
            _t3.metric("Carb",          f"{_totais.get('Carb(g)',0):.1f}g")
            _t4.metric("Gordura",       f"{_totais.get('Gordura(g)',0):.1f}g")

    # ── Botões Salvar / Limpar / Export ───────────────────────────────────
    _db1, _db2, _db3 = st.columns([2, 1, 1])
    if _db1.button("💾 Salvar dieta manual no banco", key="btn_salvar_dieta_manual",
                   type="primary", use_container_width=True):
        salvar_dieta_manual(_df_dieta_edit, _data_ref_str)
    if _db3.button("🗑️ Limpar", key="btn_limpar_dieta_manual", use_container_width=True):
        st.session_state[_cache_key] = pd.DataFrame(columns=_COLUNAS_DIETA)
        salvar_dieta_manual(pd.DataFrame(columns=_COLUNAS_DIETA), _data_ref_str)
        st.rerun()

    st.download_button(
        "⬇️ Exportar dieta manual (.csv)",
        data=_df_dieta_edit.to_csv(sep=";", index=False),
        file_name=f"dieta_manual_{_data_ref_str}.csv",
        mime="text/csv", key="btn_export_dieta_manual",
    )

    # ══════════════════════════════════════════════════════════════════════
    # FUNDAMENTOS CIENTÍFICOS DA NUTRIÇÃO
    # ══════════════════════════════════════════════════════════════════════
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

    # ══════════════════════════════════════════════════════════════════════
    # SUPLEMENTAÇÃO (incorporada aqui, aba própria removida)
    # ══════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("💊 Suplementação")
    st.caption("Apenas suplementos com evidência Grau A ou B incluídos.")
    st.dataframe(recomendar_suplementos(atleta), use_container_width=True, hide_index=True)

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


def _prescrever_cardio(fase: str, atleta, df_hist: pd.DataFrame) -> dict:
    """
    Calcula a prescrição de cardio semanal baseada em:
    - Fase atual (Bulking/Cutting/Peak Week/Recomposição/Off-Season)
    - Taxa de perda atual vs. alvo
    - Status de recuperação (VFC)
    - Efeito de interferência (Helms et al., 2014 — cycling > running)
    
    Retorna dict com: sessoes_liss, min_liss, sessoes_hiit, min_hiit,
                      kcal_estimado, modalidade_liss, protocolo_hiit,
                      zona_liss, justificativa, alerta
    """
    peso    = atleta.peso or 80.0
    vfc_at  = atleta.vfc_atual or 0
    vfc_b   = atleta.vfc_base  or 60.0
    queda_vfc = ((vfc_b - vfc_at) / vfc_b * 100) if vfc_b > 0 and vfc_at > 0 else 0
    fadiga_snc = queda_vfc > 10  # VFC caiu >10% da baseline = SNC sobrecarregado

    # Taxa de perda semanal atual (últimos 14 dias)
    taxa_perda = None
    if not df_hist.empty and "Peso" in df_hist.columns and len(df_hist) >= 2:
        df_s = df_hist.dropna(subset=["Peso"]).sort_values("Data")
        if len(df_s) >= 2:
            p_ini = float(df_s["Peso"].iloc[0])
            p_fim = float(df_s["Peso"].iloc[-1])
            n_sem = max(1, len(df_s) / 7)
            if p_ini > 0:
                taxa_perda = ((p_ini - p_fim) / p_ini * 100) / n_sem  # %/semana

    # Kcal queimadas estimadas: LISS ~7 kcal/kg/h · HIIT ~10 kcal/kg/h (Wilson et al., 2012)
    KCAL_LISS_MIN = peso * 7 / 60   # kcal por minuto de LISS
    KCAL_HIIT_MIN = peso * 10 / 60  # kcal por minuto de HIIT (+ EPOC ≈ +15%)

    resultado = {
        "sessoes_liss": 0, "min_liss": 0,
        "sessoes_hiit": 0, "min_hiit": 0,
        "kcal_estimado": 0,
        "modalidade_liss": "Bicicleta ergométrica ou caminhada inclinada",
        "protocolo_hiit": "20 s esforço máximo / 40 s recuperação ativa — 8 rounds",
        "zona_liss": "Zona 2 (60–70% FCmáx)",
        "justificativa": "",
        "alerta": None,
    }

    if fase == "Bulking":
        # Bulking: cardio mínimo para saúde cardiovascular e partição calórica
        # Sem cardio ou mínimo (2×/sem LISS leve) — não criar déficit que atrapalhe o superávit
        resultado.update({
            "sessoes_liss": 2, "min_liss": 25,
            "sessoes_hiit": 0, "min_hiit": 0,
            "zona_liss": "Zona 1–2 (50–65% FCmáx)",
            "modalidade_liss": "Caminhada (5–6 km/h) ou bicicleta baixa intensidade",
            "justificativa": (
                "**Mínimo necessário.** No bulking o cardio não deve criar déficit calórico "
                "significativo. 2 × 25 min de LISS leve mantém saúde cardiovascular, vias "
                "metabólicas de oxidação de gordura ativas e melhora a partição calórica "
                "(nutrientes → músculo, não gordura). Sem HIIT: o treino de força já provê "
                "estímulo anaeróbio suficiente. *(Helms et al., 2014; Iraki et al., 2019)*"
            ),
        })
        if fadiga_snc:
            resultado["alerta"] = "⚠️ VFC baixa — reduzir para 1 × 20 min até VFC se normalizar."

    elif fase in ("Cutting", "Pre-Contest (Cutting)"):
        # Cutting: cardio é ferramenta de apoio ao déficit — diet first
        # Progressão baseada na taxa de perda atual vs. alvo (0.5–1.0%/sem)
        if taxa_perda is not None and taxa_perda >= 0.8:
            # Perda adequada ou acima: manter volume atual (leve)
            s_liss, m_liss = 3, 35
            s_hiit, m_hiit = 1, 20
            just = "Perda dentro do alvo. Manter cardio moderado sem aumentar."
        elif taxa_perda is not None and taxa_perda >= 0.5:
            # Perda lenta: adicionar 1 sessão LISS
            s_liss, m_liss = 4, 35
            s_hiit, m_hiit = 1, 20
            just = "Perda ligeiramente abaixo do alvo. Adicionar 1 sessão LISS."
        else:
            # Platô ou sem dados: protocolo padrão cutting
            s_liss, m_liss = 4, 40
            s_hiit, m_hiit = 2, 20
            just = "Protocolo padrão cutting. Priorizar LISS — menor custo de recuperação."

        # Fadiga de SNC: suspender HIIT
        if fadiga_snc:
            s_hiit, m_hiit = 0, 0
            resultado["alerta"] = "🔴 VFC abaixo da baseline (>10%). HIIT suspenso — apenas LISS de baixa intensidade até recuperação."

        resultado.update({
            "sessoes_liss": s_liss, "min_liss": m_liss,
            "sessoes_hiit": s_hiit, "min_hiit": m_hiit,
            "zona_liss": "Zona 2 (60–70% FCmáx)",
            "modalidade_liss": "Bicicleta ergométrica (menor interferência) ou esteira inclinada",
            "protocolo_hiit": "30 s esforço máximo (Zona 5) / 90 s recuperação ativa (Zona 1) — 6–8 rounds",
            "justificativa": (
                f"{just} A dieta gera 80% do déficit — o cardio contribui com os 20% restantes "
                "para preservar LBM. Ciclismo reduz interferência vs. corrida "
                "*(Wilson et al., 2012; Helms et al., 2014 — grau A)*. "
                "HIIT máx 2×/sem para não elevar cortisol e comprometer recuperação muscular. "
                "*(Kikuchi et al., 2016)*"
            ),
        })

    elif fase == "Peak Week":
        # Peak Week: cardio MÍNIMO — depleção de glicogênio não deve vir do cardio
        # Apenas LISS muito leve para manter metabolismo sem esgotar reservas
        resultado.update({
            "sessoes_liss": 2, "min_liss": 20,
            "sessoes_hiit": 0, "min_hiit": 0,
            "zona_liss": "Zona 1 (50–55% FCmáx) — walking apenas",
            "modalidade_liss": "Caminhada leve (4–5 km/h) — sem impacto",
            "justificativa": (
                "**Peak Week: cardio mínimo ou zero.** A depleção de glicogênio é feita pela "
                "dieta (baixo CHO dias 1–3), não pelo cardio. Cardio excessivo nesta semana "
                "reduz fullness muscular no palco. Apenas caminhada leve pode ser mantida "
                "para controle hídrico e psicológico. *(Chappell et al., 2018)*"
            ),
        })
        resultado["alerta"] = "⚡ Dias 4–5 (Carb-Up): suspender todo cardio — maximizar supercompensação de glicogênio."

    elif fase == "Recomposição":
        resultado.update({
            "sessoes_liss": 3, "min_liss": 30,
            "sessoes_hiit": 1, "min_hiit": 15,
            "zona_liss": "Zona 2 (60–70% FCmáx)",
            "modalidade_liss": "Bicicleta ergométrica ou caminhada inclinada",
            "protocolo_hiit": "20 s esforço / 40 s recuperação — 6 rounds (Tabata modificado)",
            "justificativa": (
                "Recomposição: déficit leve (−200 kcal/dieta). Cardio complementa sem "
                "criar déficit excessivo que impeça síntese proteica. 1 sessão HIIT "
                "semanal melhora sensibilidade à insulina e oxidação de gordura. "
                "*(Barakat et al., 2020)*"
            ),
        })
        if fadiga_snc:
            resultado["sessoes_hiit"] = 0
            resultado["min_hiit"]    = 0
            resultado["alerta"] = "⚠️ VFC baixa — suspender HIIT esta semana."

    else:  # Off-Season / manutenção
        resultado.update({
            "sessoes_liss": 2, "min_liss": 30,
            "sessoes_hiit": 0, "min_hiit": 0,
            "zona_liss": "Zona 1–2 (50–65% FCmáx)",
            "modalidade_liss": "Qualquer modalidade de baixo impacto",
            "justificativa": (
                "Off-season: cardio de manutenção cardiovascular e metabólica. "
                "Mantém vias de oxidação de gordura ativas e melhora recuperação "
                "entre sessões de musculação. *(Helms et al., 2014)*"
            ),
        })

    # Calcular kcal estimado da semana
    kcal_liss = resultado["sessoes_liss"] * resultado["min_liss"] * KCAL_LISS_MIN
    kcal_hiit = resultado["sessoes_hiit"] * resultado["min_hiit"] * KCAL_HIIT_MIN * 1.15  # +15% EPOC
    resultado["kcal_estimado"] = round(kcal_liss + kcal_hiit)

    return resultado


def tab_treino(fase, atleta, df_hist):
    st.header("🏋️ Plano de Treino Semanal")
    df_treino, motivo = gerar_treino_semanal(atleta, exercicios_db)
    st.caption(motivo)
    st.dataframe(df_treino, use_container_width=True, hide_index=True)
    st.download_button("📥 Exportar CSV",
        data=df_treino.to_csv(sep=";", index=False),
        file_name=f"treino_{fase.lower().replace(' ','_')}.csv", mime="text/csv")

    # ══════════════════════════════════════════════════════════════════════
    # TREINO MANUAL — adicional ao treino automático
    # ══════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("📝 Treino Manual")
    st.caption(
        "Registre seu próprio treino aqui. "
        "Não substitui o treino automático — ambos aparecem lado a lado. "
        "Edite diretamente nas células da tabela ou importe um arquivo CSV."
    )

    # Colunas mapeadas para o banco (snake_case exibido como display)
    _COLUNAS_TREINO = ["Treino","Exercício","Séries","Reps","RIR","Descanso(s)","Músculo","Notas"]

    # Carregar do Supabase na primeira vez (cache por sessão)
    if "treino_manual_df" not in st.session_state:
        raw = carregar_treino_manual()
        if not raw.empty:
            col_map_inv = {
                "treino":"Treino","exercicio":"Exercício","series":"Séries",
                "reps":"Reps","rir":"RIR","descanso_s":"Descanso(s)",
                "musculo":"Músculo","notas":"Notas",
            }
            raw = raw.drop(columns=["id"], errors="ignore").rename(columns=col_map_inv)
            st.session_state["treino_manual_df"] = raw[[c for c in _COLUNAS_TREINO if c in raw.columns]]
        else:
            st.session_state["treino_manual_df"] = pd.DataFrame(columns=_COLUNAS_TREINO)

    # ── Import CSV ────────────────────────────────────────────────────────
    with st.expander("📂 Importar treino por CSV"):
        st.caption(
            f"O arquivo deve seguir a ordem das colunas: "
            f"`{' | '.join(_COLUNAS_TREINO)}`"
        )
        _has_header = st.checkbox(
            "O arquivo CSV possui cabeçalho (primeira linha = nomes das colunas)",
            value=True, key="treino_csv_header",
        )
        _csv_file = st.file_uploader("Selecione o arquivo .csv", type=["csv"], key="treino_csv_upload")
        if _csv_file is not None:
            try:
                _df_csv = pd.read_csv(_csv_file, sep=None, engine="python",
                                      header=0 if _has_header else None)
                if not _has_header:
                    n = min(len(_COLUNAS_TREINO), len(_df_csv.columns))
                    _df_csv.columns = list(_COLUNAS_TREINO[:n]) + list(_df_csv.columns[n:])
                _cols_ok = [c for c in _COLUNAS_TREINO if c in _df_csv.columns]
                st.session_state["treino_manual_df"] = _df_csv[_cols_ok].copy()
                st.success(f"✅ {len(_df_csv)} linhas importadas.")
            except Exception as _e:
                st.error(f"Erro ao ler CSV: {_e}")

    # ── Editor manual ─────────────────────────────────────────────────────
    st.markdown("**✏️ Editar treino manual (clique nas células para editar):**")
    _df_edit = st.data_editor(
        st.session_state["treino_manual_df"],
        num_rows="dynamic",
        use_container_width=True,
        key="treino_manual_editor",
        column_config={c: st.column_config.TextColumn(c) for c in _COLUNAS_TREINO},
    )
    st.session_state["treino_manual_df"] = _df_edit

    # ── Botões Salvar / Limpar ────────────────────────────────────────────
    _bm1, _bm2, _bm3 = st.columns([2, 1, 1])
    if _bm1.button("💾 Salvar treino manual no banco", key="btn_salvar_treino_manual",
                   type="primary", use_container_width=True):
        salvar_treino_manual(_df_edit)
    if _bm3.button("🗑️ Limpar", key="btn_limpar_treino_manual", use_container_width=True):
        st.session_state["treino_manual_df"] = pd.DataFrame(columns=_COLUNAS_TREINO)
        salvar_treino_manual(pd.DataFrame(columns=_COLUNAS_TREINO))
        st.rerun()

    # ── Export com seleção ────────────────────────────────────────────────
    st.divider()
    _tem_manual = not st.session_state["treino_manual_df"].empty
    _opcoes_export = ["🤖 Treino automático"]
    if _tem_manual:
        _opcoes_export += ["📝 Treino manual", "📋 Ambos (automático + manual)"]

    _export_choice = st.selectbox("📥 Exportar como CSV:", _opcoes_export, key="treino_export_choice")
    if _export_choice == "🤖 Treino automático":
        _df_export = df_treino; _fname = f"treino_auto_{fase.lower().replace(' ','_')}.csv"
    elif _export_choice == "📝 Treino manual":
        _df_export = st.session_state["treino_manual_df"]; _fname = f"treino_manual_{fase.lower().replace(' ','_')}.csv"
    else:
        _df_export = pd.concat(
            [df_treino.assign(Origem="Automático"),
             st.session_state["treino_manual_df"].assign(Origem="Manual")],
            ignore_index=True,
        ); _fname = f"treino_completo_{fase.lower().replace(' ','_')}.csv"

    st.download_button(
        f"⬇️ Baixar: {_export_choice}",
        data=_df_export.to_csv(sep=";", index=False),
        file_name=_fname, mime="text/csv", key="btn_export_treino_final",
    )

    # ══════════════════════════════════════════════════════════════════════
    # SEÇÃO DE CARDIO CARDIOVASCULAR
    # ══════════════════════════════════════════════════════════════════════
    st.divider()
    st.subheader("🫀 Prescrição Cardiovascular")
    st.caption(
        "Cardio é ferramenta de apoio — a dieta gera o déficit principal. "
        "Volume mínimo para atingir a meta. *(Helms et al., 2014 — grau A)*"
    )

    cardio = _prescrever_cardio(fase, atleta, df_hist)

    # Alerta de VFC/fadiga no topo
    if cardio["alerta"]:
        st.warning(cardio["alerta"])

    # ── Métricas principais ──────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    total_sessoes = cardio["sessoes_liss"] + cardio["sessoes_hiit"]
    total_min     = cardio["sessoes_liss"] * cardio["min_liss"] + \
                    cardio["sessoes_hiit"] * cardio["min_hiit"]

    c1.metric("📅 Sessões/semana",   f"{total_sessoes}",
              help="LISS + HIIT combinados")
    c2.metric("⏱ Minutos/semana",    f"{total_min} min",
              help="Tempo total de cardio na semana")
    c3.metric("🔥 Gasto estimado",   f"~{cardio['kcal_estimado']} kcal",
              help="LISS + HIIT (inclui EPOC pós-HIIT +15%)")
    c4.metric("📊 Fase",             fase)

    st.caption(cardio["justificativa"])

    # ── Tabela de sessões semanais ────────────────────────────────────────
    dias_semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

    # Distribuição inteligente de sessões
    sessoes_cardio = []

    if cardio["sessoes_liss"] > 0 or cardio["sessoes_hiit"] > 0:
        # Regra: HIIT nunca em dias consecutivos e nunca antes de treino de força pesado
        # LISS preferível nos dias de descanso do treino ou após musculação
        hiit_dias  = []
        liss_dias  = []

        # Posicionar HIIT: preferencialmente terça e sexta (longe do treino de perna)
        if cardio["sessoes_hiit"] >= 1: hiit_dias.append(1)   # Terça
        if cardio["sessoes_hiit"] >= 2: hiit_dias.append(4)   # Sexta

        # LISS: distribuir nos demais dias, preferindo dias de descanso do treino
        liss_pool = [d for d in range(7) if d not in hiit_dias]
        import random; random.seed(42)
        liss_selecionados = sorted(random.sample(liss_pool, min(cardio["sessoes_liss"], len(liss_pool))))

        for i, dia in enumerate(dias_semana):
            idx = i
            tipo = "—"
            modalidade = "—"
            duracao = "—"
            zona = "—"
            kcal = "—"
            if idx in hiit_dias:
                tipo = "🔴 HIIT"
                modalidade = "Bicicleta sprint / Esteira intervals"
                duracao = f"{cardio['min_hiit']} min"
                zona = "Zona 4–5 (80–95% FCmáx)"
                kcal = f"~{round(cardio['min_hiit'] * atleta.peso * 10 / 60 * 1.15)} kcal (+EPOC)"
            elif idx in liss_selecionados:
                tipo = "🟢 LISS"
                modalidade = cardio["modalidade_liss"]
                duracao = f"{cardio['min_liss']} min"
                zona = cardio["zona_liss"]
                kcal = f"~{round(cardio['min_liss'] * atleta.peso * 7 / 60)} kcal"
            sessoes_cardio.append({
                "Dia": dia, "Tipo": tipo,
                "Modalidade": modalidade, "Duração": duracao,
                "Zona FC": zona, "Gasto est.": kcal
            })

        df_cardio = pd.DataFrame(sessoes_cardio)
        st.dataframe(df_cardio, use_container_width=True, hide_index=True)

    # ── Protocolo HIIT detalhado ──────────────────────────────────────────
    if cardio["sessoes_hiit"] > 0:
        with st.expander("🔴 Protocolo HIIT — Detalhado"):
            st.markdown(f"""
**Protocolo:** {cardio['protocolo_hiit']}

| Fase | Duração | Intensidade | FC alvo |
|------|---------|-------------|---------|
| Aquecimento | 5 min | Zona 1 (50–55% FCmáx) | Gradual |
| Esforço (on) | 20–30 s | Zona 5 (≥ 90% FCmáx) | Máxima |
| Recuperação (off) | 40–90 s | Zona 1 (< 55% FCmáx) | < 120 bpm |
| Rounds | 6–8 rounds | — | — |
| Resfriamento | 5 min | Zona 1 | Gradual |

**Modalidades recomendadas (menor interferência muscular):**
- ✅ Bicicleta ergométrica — menor interferência em hipertrofia *(Wilson et al., 2012)*
- ✅ Remo ergométrico — full body, sem impacto
- ✅ Assault bike (air bike) — alta demanda cardiovascular sem corrida
- ⚠️ Corrida — evitar se priorizando hipertrofia de pernas (maior interferência)
- ❌ HIIT em dias consecutivos — risco de overreaching do SNC

**EPOC (Excess Post-Exercise Oxygen Consumption):** o corpo continua queimando calorias
por 12–24h após o HIIT — estimativa +15% sobre o gasto da sessão.
*(Tremblay et al., 1994)*
            """)

    # ── Protocolo LISS detalhado ─────────────────────────────────────────
    if cardio["sessoes_liss"] > 0:
        with st.expander("🟢 Protocolo LISS — Detalhado"):
            # Calcular FC alvo usando Karvonen se disponível
            fc_rep    = int(atleta.fc_repouso or 55)
            idade_est = 30  # fallback
            fc_max_k  = 208 - 0.7 * idade_est
            fcr       = fc_max_k - fc_rep
            fc_liss_min = int(fcr * 0.60 + fc_rep)
            fc_liss_max = int(fcr * 0.70 + fc_rep)

            st.markdown(f"""
**Modalidade:** {cardio["modalidade_liss"]}  
**Duração:** {cardio["min_liss"]} min · **Zona:** {cardio["zona_liss"]}  
**FC alvo (Karvonen):** {fc_liss_min}–{fc_liss_max} bpm *(configure sua FC repouso no Perfil para precisão)*

| Aspecto | Detalhe |
|---------|---------|
| Intensidade | Deve conseguir manter uma conversa sem ofegar |
| Timing | Preferencialmente após musculação ou em dias separados |
| Jejum | Cardio em jejum NÃO tem vantagem sobre alimentado para perda total de gordura *(Schoenfeld et al., 2014)* |
| Progressão | Aumentar 5 min/sessão se taxa de perda < 0.5%/semana |
| Máximo recomendado | 5–6 sessões × 45 min = ≈ 225–270 min/semana |

**Por que LISS é preferido no cutting vs. HIIT para bodybuilders:**
- Menor elevação de cortisol → menos catabolismo muscular
- Não compete pelo mesmo substrato energético que o treino de força
- Permite recuperação muscular durante a sessão
- Menor risco de lesão em estado de déficit calórico
- *(Helms et al., 2014 — grau A; Wilson et al., 2012 — grau B)*
            """)

    # ── Calculadora de déficit de cardio ─────────────────────────────────
    with st.expander("🧮 Calculadora de Gasto Cardio"):
        st.caption("Estime quanto cardio adicionar para fechar um déficit calórico específico.")
        col_a, col_b = st.columns(2)
        with col_a:
            deficit_alvo = st.number_input(
                "Déficit calórico adicional alvo (kcal/sem)",
                min_value=0, max_value=3500, value=500, step=100,
                help="Ex: 500 kcal/semana ≈ −0.07 kg/sem extra"
            )
            modalidade_calc = st.selectbox(
                "Modalidade",
                ["LISS — Bicicleta (7 kcal/kg/h)",
                 "LISS — Caminhada inclinada (5 kcal/kg/h)",
                 "LISS — Natação (8 kcal/kg/h)",
                 "HIIT — Sprint intervals (10 kcal/kg/h + EPOC)"]
            )
        with col_b:
            peso_calc = st.number_input("Peso (kg)", value=float(atleta.peso or 80.0),
                                         min_value=40.0, max_value=200.0, step=0.5)
            sessoes_calc = st.number_input("Nº de sessões/semana", min_value=1, max_value=7, value=3)

        # Extrair taxa
        taxa_map = {
            "LISS — Bicicleta (7 kcal/kg/h)":          7,
            "LISS — Caminhada inclinada (5 kcal/kg/h)": 5,
            "LISS — Natação (8 kcal/kg/h)":             8,
            "HIIT — Sprint intervals (10 kcal/kg/h + EPOC)": 10 * 1.15,
        }
        taxa_kcal_h = taxa_map[modalidade_calc]
        kcal_por_min = peso_calc * taxa_kcal_h / 60

        if deficit_alvo > 0 and sessoes_calc > 0:
            min_por_sessao = round(deficit_alvo / (sessoes_calc * kcal_por_min))
            st.success(
                f"**{sessoes_calc} sessão(ões) de {min_por_sessao} min** cada "
                f"= ~{deficit_alvo} kcal/semana extra "
                f"(~{round(deficit_alvo/7)} kcal/dia)"
            )
            if min_por_sessao > 60:
                st.warning(
                    f"⚠️ {min_por_sessao} min/sessão é longo. Considere aumentar o número de "
                    "sessões ou ajustar o déficit pela dieta para reduzir a duração."
                )

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

    # ── Verificar dados disponíveis ───────────────────────────────────────────
    ultimo = carregar_ultimo_registro()
    variaveis = {
        "VFC Noturna (ms)":     float(ultimo.get("vfc_noturna")   or 0),
        "Sleep Score":          float(ultimo.get("sleep_score")   or 0),
        "Recovery Time (h)":    float(ultimo.get("recovery_time") or 0),
        "FC Repouso (bpm)":     float(ultimo.get("fc_repouso")    or 0),
        "Volume Load (treino)": float(ultimo.get("carga_treino")  or 0),
    }
    faltando = [k for k, v in variaveis.items() if v == 0]

    if faltando:
        with st.warning(f"⚠️ **Dados insuficientes para análise completa.** Preencha na aba 📁 Registros:"):
            for f_ in faltando:
                st.write(f"  • {f_}")

    # Só exibe a análise se pelo menos VFC + sleep ou recovery existirem
    tem_vfc  = variaveis["VFC Noturna (ms)"] > 0
    tem_rec  = variaveis["Recovery Time (h)"] > 0 or variaveis["Sleep Score"] > 0

    if not tem_vfc and not tem_rec:
        st.info("Registre pelo menos **VFC Noturna** ou **Sleep Score + Recovery Time** para ver o status de recuperação.")
        with st.expander("📖 Por que esses dados são importantes?"):
            st.markdown("""
**VFC (Variabilidade da Frequência Cardíaca)** reflete o equilíbrio do sistema nervoso autônomo.
Uma queda de >10% em relação à baseline indica fadiga do SNC — não apenas muscular. *(Flatt & Esco, 2016)*

**Sleep Score** quantifica a qualidade do sono, que é o principal fator de recuperação hormonal
(GH liberado principalmente no sono profundo). *(Dattilo et al., 2011)*

**Recovery Time** (Garmin) integra múltiplos parâmetros em uma estimativa de horas até
a próxima sessão intensa. *(Flatt et al., 2018)*
            """)
        return

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
        else:
            st.info("ACWR requer ≥ 7 registros com Volume Load.")
        st.caption(acwr_status)

    with col_c:
        st.subheader("📊 CV da VFC (7d)")
        if cv_val is not None:
            cor = "#E57373" if cv_val>10 else ("#FFD54F" if cv_val>7 else "#81C784")
            st.markdown(f"<h1 style='text-align:center;color:{cor}'>{cv_val}%</h1>", unsafe_allow_html=True)
        else:
            st.info("CV-VFC requer ≥ 7 registros com VFC.")
        st.caption(cv_status)

    st.divider()
    st.subheader("📖 Fundamentos Científicos da Recuperação")

    with st.expander("VFC como Indicador de Recuperação do SNC — Flatt & Esco (2016)", expanded=True):
        vfc_b = p.get("vfc_base",0)
        vfc_a = p.get("vfc_at",0)
        delta = round(((vfc_a - vfc_b) / vfc_b) * 100, 1) if vfc_b > 0 and vfc_a > 0 else None
        if delta is not None:
            cor_delta = "🟢" if delta >= -5 else ("🟡" if delta >= -10 else "🔴")
            st.markdown(f"**VFC Baseline:** {vfc_b} ms | **VFC Atual:** {vfc_a} ms | **Δ:** {cor_delta} {delta:+.1f}%")
        else:
            st.markdown("*Configure VFC Baseline no Perfil e registre VFC Noturna para ver a análise.*")
        st.markdown("""
A VFC reflete o equilíbrio simpático/parassimpático. Quedas > 10% indicam fadiga autonômica do SNC.

**Pontuação de fadiga (0-10 pontos):**
- VFC < 10% abaixo da baseline → +2 pts / < 20% → +3 pts
- Sleep Score < 60 → +2 pts | < 70 → +1 pt
- Recovery Time > 48h → +2 pts | > 36h → +1 pt
- ACWR > 1.5 → +1 pt / CV-VFC > 10% → +1 pt

**Decisão:** ≥5 pts = repouso total | 3-4 pts = Zona 2 | <3 pts = treinar normalmente
        """)

    with st.expander("ACWR — Gabbett (2016)"):
        st.markdown(f"""
**Acute:Chronic Workload Ratio = Carga aguda (7d) ÷ Carga crônica (28d)**

| Zona | ACWR | Interpretação |
|---|---|---|
| 🔵 Subtreino | < 0.8 | Aumentar volume gradualmente |
| 🟢 Ótimo | 0.8–1.3 | Zona segura de adaptação |
| 🟡 Atenção | 1.3–1.5 | Monitorar overreaching |
| 🔴 Perigo | > 1.5 | Alto risco de lesão |

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
    st.header("📈 Evolução")

    # Carregar dados ricos de medidas_atleta
    df_med = carregar_todos_registros()

    def _plot_base(fig, title):
        fig.update_layout(
            title=title,
            plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
            hovermode="x unified",
            legend=dict(orientation="h", y=1.1, x=1, xanchor="right"),
            margin=dict(l=20,r=20,t=50,b=20),
        )
        return fig

    def _has_col(df, *cols):
        return not df.empty and all(c in df.columns for c in cols) and \
               any(pd.to_numeric(df[c], errors='coerce').dropna().gt(0).any() for c in cols)

    if df_med.empty:
        st.info("📊 Faça pelo menos 2 registros para visualizar os gráficos de evolução.")
        return

    df_s = df_med.sort_values("data").copy()
    for c in df_s.select_dtypes(include="object").columns:
        try: df_s[c] = pd.to_numeric(df_s[c], errors="ignore")
        except: pass

    # ── Gráfico 1: Composição Corporal ───────────────────────────────────────
    st.subheader("⚖️ Composição Corporal")
    if _has_col(df_s, "peso"):
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=df_s["data"], y=pd.to_numeric(df_s["peso"],errors="coerce"),
            mode="lines+markers", name="Peso (kg)", yaxis="y1",
            line=dict(color="#42A5F5",width=2), marker=dict(size=6)))
        for col, cor, label in [
            ("bf_final","#FFA726","BF% Final"),
            ("bf_bioimpedancia","#FF7043","BF% Bio"),
            ("bf_calculado","#FFCA28","BF% Dobras"),
        ]:
            if col in df_s.columns and pd.to_numeric(df_s[col],errors="coerce").dropna().gt(0).any():
                fig.add_trace(go.Scatter(x=df_s["data"], y=pd.to_numeric(df_s[col],errors="coerce"),
                    mode="lines+markers", name=label, yaxis="y2",
                    line=dict(color=cor,width=2,dash="dash"), marker=dict(size=5)))
        for col, cor, label in [
            ("massa_livre_gordura","#66BB6A","FFM (kg)"),
            ("massa_gordura","#EF5350","FM (kg)"),
        ]:
            if col in df_s.columns and pd.to_numeric(df_s[col],errors="coerce").dropna().gt(0).any():
                fig.add_trace(go.Scatter(x=df_s["data"], y=pd.to_numeric(df_s[col],errors="coerce"),
                    mode="lines+markers", name=label, yaxis="y1",
                    line=dict(color=cor,width=1.5,dash="dot"), marker=dict(size=5)))
        fig.update_layout(
            yaxis=dict(title="Peso / FM / FFM (kg)", tickfont=dict(color="#42A5F5")),
            yaxis2=dict(title="BF (%)", tickfont=dict(color="#FFA726"), overlaying="y", side="right"),
        )
        st.plotly_chart(_plot_base(fig, "Peso, BF%, FM e FFM"), use_container_width=True)

    # ── Gráfico 2: Água Corporal (BIA avançada) ───────────────────────────────
    cols_agua = ["agua_total","agua_intracelular","agua_extracelular"]
    if _has_col(df_s, *[c for c in cols_agua if c in df_s.columns]):
        st.subheader("💧 Água Corporal")
        st.caption("*ICW/ECW ratio crítico na Peak Week — alvo: ICW/ECW > 1.90 no dia do show. (Ribas et al., 2022 — PMC8880471)*")
        fig_w = go.Figure()
        cores_agua = {"agua_total":"#29B6F6","agua_intracelular":"#26A69A","agua_extracelular":"#EF5350"}
        labels_agua = {"agua_total":"TBW (L)","agua_intracelular":"ICW (L)","agua_extracelular":"ECW (L)"}
        for col in cols_agua:
            if col in df_s.columns:
                fig_w.add_trace(go.Scatter(x=df_s["data"], y=pd.to_numeric(df_s[col],errors="coerce"),
                    mode="lines+markers", name=labels_agua[col],
                    line=dict(color=cores_agua[col],width=2), marker=dict(size=6)))
        if "agua_intracelular" in df_s.columns and "agua_extracelular" in df_s.columns:
            icw = pd.to_numeric(df_s["agua_intracelular"],errors="coerce")
            ecw = pd.to_numeric(df_s["agua_extracelular"],errors="coerce")
            ratio = icw / ecw.replace(0, float("nan"))
            fig_w.add_trace(go.Scatter(x=df_s["data"], y=ratio,
                mode="lines+markers", name="ICW/ECW Ratio", yaxis="y2",
                line=dict(color="#AB47BC",width=2,dash="dash"), marker=dict(size=5)))
            fig_w.update_layout(
                yaxis2=dict(title="ICW/ECW Ratio", tickfont=dict(color="#AB47BC"),
                            overlaying="y", side="right"))
        st.plotly_chart(_plot_base(fig_w, "Água Corporal Total, Intracelular e Extracelular"), use_container_width=True)

    # ── Gráfico 3: Ângulo de Fase e Impedância ────────────────────────────────
    if _has_col(df_s, "angulo_fase"):
        st.subheader("⚡ Ângulo de Fase (BIA)")
        st.caption("*PhA > 7° em atletas de resistência. Valores ≥ 9.6° observados em bodybuilders no dia do show. (Kyle et al., 2005; Ribas et al., 2022)*")
        fig_pha = go.Figure()
        fig_pha.add_trace(go.Scatter(x=df_s["data"], y=pd.to_numeric(df_s["angulo_fase"],errors="coerce"),
            mode="lines+markers", name="Ângulo de Fase (°)",
            line=dict(color="#FFCA28",width=2), marker=dict(size=8)))
        for col, cor, label in [("resistencia","#78909C","R (Ω)"),("reactancia","#80DEEA","Xc (Ω)")]:
            if col in df_s.columns and pd.to_numeric(df_s[col],errors="coerce").dropna().gt(0).any():
                fig_pha.add_trace(go.Scatter(x=df_s["data"], y=pd.to_numeric(df_s[col],errors="coerce"),
                    mode="lines", name=label, yaxis="y2",
                    line=dict(color=cor,width=1.5,dash="dot")))
        fig_pha.update_layout(
            yaxis2=dict(title="R / Xc (Ω)", overlaying="y", side="right"))
        fig_pha.add_hrect(y0=7, y1=12, fillcolor="rgba(102,187,106,0.15)",
                          line_width=0, annotation_text="Referência atletas ≥7°", annotation_position="top left")
        st.plotly_chart(_plot_base(fig_pha, "Ângulo de Fase, Resistência e Reactância"), use_container_width=True)

    # ── Gráfico 4: Dobras Cutâneas ────────────────────────────────────────────
    dobras_cols = ["dobra_peitoral","dobra_axilar","dobra_tricipital","dobra_subescapular",
                   "dobra_abdominal","dobra_suprailiaca","dobra_coxa","dobra_bicipital"]
    dobras_disp = [c for c in dobras_cols if c in df_s.columns and
                   pd.to_numeric(df_s[c],errors="coerce").dropna().gt(0).any()]
    if dobras_disp:
        st.subheader("🔬 Dobras Cutâneas (mm)")
        cores_d = ["#EF5350","#FF7043","#FFA726","#FFCA28","#66BB6A","#29B6F6","#5C6BC0","#AB47BC"]
        fig_d = go.Figure()
        for i, col in enumerate(dobras_disp):
            lbl = col.replace("dobra_","").capitalize()
            fig_d.add_trace(go.Scatter(x=df_s["data"], y=pd.to_numeric(df_s[col],errors="coerce"),
                mode="lines+markers", name=lbl,
                line=dict(color=cores_d[i % len(cores_d)],width=2), marker=dict(size=5)))
        # Soma total das dobras disponíveis
        df_soma = sum(pd.to_numeric(df_s[c],errors="coerce").fillna(0) for c in dobras_disp)
        fig_d.add_trace(go.Scatter(x=df_s["data"], y=df_soma,
            mode="lines", name="Soma total (mm)", yaxis="y2",
            line=dict(color="white",width=2,dash="dash")))
        fig_d.update_layout(
            yaxis2=dict(title="Soma (mm)", overlaying="y", side="right"))
        st.plotly_chart(_plot_base(fig_d, "Evolução das Dobras Cutâneas (mm)"), use_container_width=True)

    # ── Gráfico 5: Circunferências ────────────────────────────────────────────
    circ_cols = ["cintura","ombros","peito","quadril","biceps_d","coxa_d","panturrilha_d"]
    circ_disp = [c for c in circ_cols if c in df_s.columns and
                 pd.to_numeric(df_s[c],errors="coerce").dropna().gt(0).any()]
    if circ_disp:
        st.subheader("📐 Circunferências (cm)")
        cores_c = ["#EF5350","#42A5F5","#66BB6A","#FFA726","#AB47BC","#29B6F6","#FFCA28"]
        fig_c = go.Figure()
        for i, col in enumerate(circ_disp):
            fig_c.add_trace(go.Scatter(x=df_s["data"], y=pd.to_numeric(df_s[col],errors="coerce"),
                mode="lines+markers", name=col.replace("_d","").capitalize(),
                line=dict(color=cores_c[i % len(cores_c)],width=2), marker=dict(size=6)))
        st.plotly_chart(_plot_base(fig_c, "Evolução das Circunferências (cm)"), use_container_width=True)

    # ── Gráfico 6: Proporções Estéticas ──────────────────────────────────────
    if _has_col(df_s, "cintura","ombros"):
        st.subheader("🌀 Razão Áurea — Proporções")
        ratio_oc = pd.to_numeric(df_s["ombros"],errors="coerce") / \
                   pd.to_numeric(df_s["cintura"],errors="coerce").replace(0, float("nan"))
        fig_ra = go.Figure()
        fig_ra.add_trace(go.Scatter(x=df_s["data"], y=ratio_oc,
            mode="lines+markers", name="Ombro/Cintura",
            line=dict(color="#FFCA28",width=2), marker=dict(size=7)))
        if _has_col(df_s, "quadril","cintura"):
            ratio_qc = pd.to_numeric(df_s["quadril"],errors="coerce") / \
                       pd.to_numeric(df_s["cintura"],errors="coerce").replace(0, float("nan"))
            fig_ra.add_trace(go.Scatter(x=df_s["data"], y=ratio_qc,
                mode="lines+markers", name="Quadril/Cintura",
                line=dict(color="#AB47BC",width=2), marker=dict(size=7)))
        fig_ra.add_hline(y=PHI, line_dash="dash", line_color="#29B6F6",
                         annotation_text=f"φ = {PHI} (Razão Áurea)", annotation_position="right")
        st.plotly_chart(_plot_base(fig_ra, "Evolução das Proporções Estéticas vs. Razão Áurea"), use_container_width=True)

    # ── Gráfico 7: Recuperação (VFC, Sleep, Recovery) ─────────────────────────
    rec_cols = [c for c in ["vfc_noturna","sleep_score","recovery_time","fc_repouso"]
                if c in df_s.columns and pd.to_numeric(df_s[c],errors="coerce").dropna().gt(0).any()]
    if rec_cols:
        st.subheader("🎯 Dados de Recuperação")
        fig_r = go.Figure()
        cfg_rec = {
            "vfc_noturna":   ("#00e676","VFC Noturna (ms)","y1"),
            "sleep_score":   ("#CE93D8","Sleep Score","y1"),
            "recovery_time": ("#80DEEA","Recovery Time (h)","y2"),
            "fc_repouso":    ("#FF7043","FC Repouso (bpm)","y2"),
            "carga_treino":  ("#EF5350","Volume Load","y2"),
        }
        for col in rec_cols:
            cfg = cfg_rec.get(col, ("#FFFFFF",col,"y1"))
            fig_r.add_trace(go.Scatter(x=df_s["data"], y=pd.to_numeric(df_s[col],errors="coerce"),
                mode="lines+markers", name=cfg[1], yaxis=cfg[2],
                line=dict(color=cfg[0],width=2), marker=dict(size=5)))
        if "carga_treino" in df_s.columns and pd.to_numeric(df_s["carga_treino"],errors="coerce").dropna().gt(0).any():
            fig_r.add_trace(go.Bar(x=df_s["data"], y=pd.to_numeric(df_s["carga_treino"],errors="coerce"),
                name="Volume Load", yaxis="y2", opacity=0.3, marker_color="#EF5350"))
        fig_r.update_layout(
            yaxis=dict(title="VFC / Sleep", tickfont=dict(color="#00e676")),
            yaxis2=dict(title="Recovery / FC / Volume", overlaying="y", side="right"))
        st.plotly_chart(_plot_base(fig_r, "Dados de Recuperação"), use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# ABA — REGISTROS UNIFICADOS
# ─────────────────────────────────────────────────────────────────────────────




def tab_registros(p: dict, atleta, perfil: dict):
    """
    Aba unificada de registros.
    Padrão correto Streamlit: botões setam um flag _reg_pending no session_state
    → st.rerun() → no próximo ciclo, ANTES de qualquer widget ser instanciado,
    os valores são copiados para os reg_* → widgets renderizam com os novos valores.
    """
    st.header("📁 Registros")

    FLOAT_FIELDS = [
        "peso","bf_bioimpedancia","bf_calculado","bf_final",
        "massa_gordura","massa_livre_gordura",
        "agua_total","agua_intracelular","agua_extracelular",
        "angulo_fase","resistencia","reactancia","carga_treino","vfc_noturna",
        "dobra_peitoral","dobra_axilar","dobra_tricipital","dobra_subescapular",
        "dobra_abdominal","dobra_suprailiaca","dobra_coxa","dobra_bicipital",
        "cintura","ombros","peito","quadril","biceps_d","coxa_d","panturrilha_d","pescoco",
    ]
    INT_FIELDS   = ["sleep_score","recovery_time","fc_repouso"]
    META_FIELDS  = ["reg_hora","reg_notas","reg_bf_formula_sel"]

    # ─── PASSO 1: processar flag ANTES de qualquer widget ────────────────────
    # Quando _reg_pending existe, este é o início de um novo ciclo limpo.
    # Podemos escrever livremente nos reg_* porque nenhum widget foi criado ainda.
    if "_reg_pending" in st.session_state:
        rec = st.session_state.pop("_reg_pending")
        if rec is None:
            # limpar tudo (novo registro) — hora pré-preenchida com agora
            for k in FLOAT_FIELDS:
                st.session_state[f"reg_{k}"] = 0.0
            for k in INT_FIELDS:
                st.session_state[f"reg_{k}"] = 0
            st.session_state["reg_hora"]           = datetime.now().strftime("%H:%M")
            st.session_state["reg_notas"]          = ""
            st.session_state["reg_bf_formula_sel"] = "jp7"
        else:
            # carregar valores do registro
            for k in FLOAT_FIELDS:
                try:    st.session_state[f"reg_{k}"] = float(rec.get(k) or 0)
                except: st.session_state[f"reg_{k}"] = 0.0
            for k in INT_FIELDS:
                try:    st.session_state[f"reg_{k}"] = int(rec.get(k) or 0)
                except: st.session_state[f"reg_{k}"] = 0
            st.session_state["reg_hora"]           = str(rec.get("hora_registro") or "")
            st.session_state["reg_notas"]          = str(rec.get("notas") or "")
            st.session_state["reg_bf_formula_sel"] = str(rec.get("bf_formula") or "jp7")

    # ─── Estado de edição ─────────────────────────────────────────────────────
    if "reg_editando" not in st.session_state:
        st.session_state["reg_editando"] = None

    editando  = st.session_state["reg_editando"]
    is_edicao = editando is not None

    # Garantir que reg_hora tenha a hora atual para novos registros
    if not is_edicao and "reg_hora" not in st.session_state:
        st.session_state["reg_hora"] = datetime.now().strftime("%H:%M")

    # ─── Histórico ───────────────────────────────────────────────────────────
    st.subheader("📋 Histórico de Registros")
    st.caption("Clique em uma linha para carregá-la no formulário abaixo.")

    df_all = carregar_todos_registros()

    if df_all.empty:
        st.info("Nenhum registro ainda. Preencha o formulário abaixo.")
    else:
        cols_pref = [
            "data","hora_registro","peso","bf_final","bf_bioimpedancia","bf_calculado",
            "massa_gordura","massa_livre_gordura",
            "angulo_fase","agua_total","agua_intracelular","agua_extracelular",
            "carga_treino","vfc_noturna","sleep_score","recovery_time","fc_repouso",
            "dobra_peitoral","dobra_axilar","dobra_tricipital","dobra_subescapular",
            "dobra_abdominal","dobra_suprailiaca","dobra_coxa","dobra_bicipital",
            "cintura","ombros","peito","quadril","biceps_d","coxa_d","panturrilha_d",
            "notas",
        ]
        cols_ok  = ["id"] + [c for c in cols_pref if c in df_all.columns]
        df_disp  = df_all[cols_ok].sort_values("data", ascending=False) if "data" in df_all.columns else df_all[cols_ok]

        ev = st.dataframe(
            df_disp.drop(columns=["id"], errors="ignore"),
            on_select="rerun", selection_mode="single-row",
            use_container_width=True, hide_index=True,
        )

        if ev.selection.rows:
            row   = df_disp.iloc[ev.selection.rows[0]].to_dict()
            row_id = str(row.get("id",""))
            cur_id = str(editando.get("id","")) if is_edicao else None
            if row_id != cur_id:
                # Nova seleção: salvar editando e agendar carga via flag
                st.session_state["reg_editando"]  = row
                st.session_state["_reg_pending"]  = row
                st.rerun()

    st.divider()

    # ─── Cabeçalho do formulário ──────────────────────────────────────────────
    if is_edicao:
        st.subheader("✏️ Editando Registro")
        h_col, d_col = st.columns([4, 1])
        h_col.info(f"📅 {editando.get('data','')} {editando.get('hora_registro','')} — edite e clique **Atualizar**.")
        if d_col.button("🗑️ Deletar", type="secondary", use_container_width=True, key="btn_del"):
            deletar_registro_unificado(str(editando["id"]))
            st.session_state["reg_editando"] = None
            st.session_state["_reg_pending"] = None
            st.rerun()
    else:
        st.subheader("➕ Novo Registro")

    # ─── Botão de pré-preenchimento — FORA do form (não dispara rerun no Tab) ─
    _fc1, _fc2 = st.columns([4, 1])
    _fc1.caption(
        "💡 Preencha os campos e clique **Salvar**. "
        "Use **📋 Último registro** para copiar os valores mais recentes. "
        "Pressione Tab livremente entre campos — os valores são preservados."
    )
    if _fc2.button("📋 Último registro", key="fill_all", use_container_width=True):
        st.session_state["_reg_pending"] = carregar_ultimo_registro()
        st.rerun()

    # ─── FORMULÁRIO ──────────────────────────────────────────────────────────
    # st.form() agrupa todos os inputs: nenhum rerun ocorre ao pressionar Tab ou
    # ao mudar de campo. O rerun só é disparado quando o usuário clica em Salvar.
    # Isso resolve definitivamente a perda de valores ao navegar com Tab.
    sexo  = p.get("sexo","Masculino")
    idade = p.get("idade", 30)
    now   = datetime.now()
    _rec_key = str(editando.get("id","new")) if is_edicao else "new"

    with st.form("reg_form", border=True):
        # ── DATA E HORA ──────────────────────────────────────────────────────
        st.markdown("#### 📅 Data e Hora")
        col_d, col_h = st.columns(2)
        with col_d:
            if is_edicao:
                data_default = datetime.strptime(
                    str(editando.get("data", now.strftime("%Y-%m-%d"))), "%Y-%m-%d"
                ).date()
            else:
                data_default = now.date()
            data_reg = st.date_input("Data", value=data_default, key=f"reg_data_{_rec_key}")
        with col_h:
            hora_reg = st.text_input("Hora (HH:MM)", key="reg_hora")

        # ══ GRUPO 1 — COMPOSIÇÃO CORPORAL ════════════════════════════════════
        st.divider()
        st.markdown("#### ⚖️ Composição Corporal")
        st.caption("Dados diretos da balança de bioimpedância ou calculados por dobras.")

        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            peso                = st.number_input("Peso (kg)",         min_value=0.0, max_value=300.0, step=0.05, format="%.2f", key="reg_peso")
            massa_gordura       = st.number_input("FM — Gordura (kg)", min_value=0.0, step=0.1, key="reg_massa_gordura")
            massa_livre_gordura = st.number_input("FFM — Magra (kg)",  min_value=0.0, step=0.1, key="reg_massa_livre_gordura")
        with cc2:
            bf_bio = st.number_input("BF% Bioimpedância", min_value=0.0, max_value=60.0, step=0.1,
                key="reg_bf_bioimpedancia", help="Valor direto do aparelho.")
            from calculos_fisio import FORMULAS_DOBRAS
            opcoes_f  = [(fid, fi["nome"]) for fid, fi in FORMULAS_DOBRAS.items()
                         if fi.get("campos_masc" if sexo=="Masculino" else "campos_fem")]
            labels_f  = [v for _, v in opcoes_f]; ids_f = [k for k, _ in opcoes_f]
            cur_f     = st.session_state.get("reg_bf_formula_sel", "jp7")
            idx_f     = ids_f.index(cur_f) if cur_f in ids_f else 0
            formula_lbl = st.selectbox("Fórmula dobras", labels_f, index=idx_f, key="reg_bf_formula_sel")
            formula_id  = ids_f[labels_f.index(formula_lbl)]
            bf_calc_input = st.number_input("BF% Dobras (calculado)", min_value=0.0, max_value=60.0, step=0.1,
                key="reg_bf_calculado", help="Calculado automaticamente ao salvar se dobras preenchidas.")
        with cc3:
            bf_final_input = st.number_input("BF% Final (para cálculos)", min_value=0.0, max_value=60.0, step=0.1,
                key="reg_bf_final", help="0 = média automática Bio+Dobras.")
            st.markdown("**BIA Avançada**")
            st.caption("R, Xc e ângulo de fase — InBody / Tanita profissional.")
            resistencia = st.number_input("Resistência R (Ω)",  min_value=0.0, step=1.0,  key="reg_resistencia")
            reactancia  = st.number_input("Reactância Xc (Ω)", min_value=0.0, step=0.5,  key="reg_reactancia")
            angulo_fase = st.number_input("Ângulo de Fase (°)", min_value=0.0, max_value=20.0, step=0.1,
                key="reg_angulo_fase", help="Atletas: 7–12°. Bodybuilder show-day: 9.6–11.2°.")

        st.markdown("**💧 Água Corporal**")
        st.caption("TBW = ICW + ECW. Peak Week: ICW/ECW ≥ 1.90. *(Ribas et al., 2022)*")
        cw1, cw2, cw3 = st.columns(3)
        agua_total = cw1.number_input("TBW — Total (L)",        min_value=0.0, step=0.1, key="reg_agua_total")
        agua_intra = cw2.number_input("ICW — Intracelular (L)", min_value=0.0, step=0.1, key="reg_agua_intracelular")
        agua_extra = cw3.number_input("ECW — Extracelular (L)", min_value=0.0, step=0.1, key="reg_agua_extracelular")

        # ══ GRUPO 2 — RECUPERAÇÃO ════════════════════════════════════════════
        st.divider()
        st.markdown("#### 🎯 Dados de Recuperação")
        rc1, rc2, rc3 = st.columns(3)
        carga_treino  = rc1.number_input("Volume Load (kg×reps)", min_value=0.0, step=10.0, key="reg_carga_treino")
        vfc_noturna   = rc1.number_input("VFC Noturna (ms)",      min_value=0.0, step=1.0,  key="reg_vfc_noturna")
        sleep_score   = rc2.number_input("Sleep Score (0–100)",   min_value=0, max_value=100, step=1, key="reg_sleep_score")
        recovery_time = rc2.number_input("Recovery Time (h)",     min_value=0, step=1, key="reg_recovery_time")
        fc_repouso    = rc3.number_input("FC Repouso (bpm)",      min_value=0, step=1, key="reg_fc_repouso")

        # ══ GRUPO 3 — DOBRAS CUTÂNEAS ════════════════════════════════════════
        st.divider()
        st.markdown("#### 🔬 Dobras Cutâneas (mm)")
        st.caption("Plicômetro, lado direito. Todos opcionais. BF% calculado ao salvar.")
        db1, db2, db3, db4 = st.columns(4)
        campos_dobras = [
            ("dobra_peitoral","Peitoral",db1),("dobra_axilar","Axilar",db2),
            ("dobra_tricipital","Tricipital",db3),("dobra_subescapular","Subescapular",db4),
            ("dobra_abdominal","Abdominal",db1),("dobra_suprailiaca","Suprailiaca",db2),
            ("dobra_coxa","Coxa",db3),("dobra_bicipital","Bíceps (Durnin)",db4),
        ]
        dobras_vals = {}
        for campo, label, col in campos_dobras:
            with col:
                dobras_vals[campo] = st.number_input(label, min_value=0.0, step=0.5, key=f"reg_{campo}")

        # ══ GRUPO 4 — CIRCUNFERÊNCIAS ════════════════════════════════════════
        st.divider()
        st.markdown("#### 📐 Circunferências (cm)")
        ci1, ci2, ci3, ci4 = st.columns(4)
        campos_circ = [
            ("cintura","Cintura",ci1),("ombros","Ombros",ci2),
            ("peito","Peito",ci3),("quadril","Quadril",ci4),
            ("biceps_d","Bíceps D",ci1),("coxa_d","Coxa D",ci2),
            ("panturrilha_d","Panturrilha D",ci3),("pescoco","Pescoço",ci4),
        ]
        circ_vals = {}
        for campo, label, col in campos_circ:
            with col:
                circ_vals[campo] = st.number_input(label, min_value=0.0, step=0.5, key=f"reg_{campo}")

        # ── Notas ─────────────────────────────────────────────────────────────
        st.divider()
        notas = st.text_area("📝 Notas", height=70, key="reg_notas")

        # ── Botão Salvar (dentro do form — único evento que dispara rerun) ────
        st.divider()
        btn_label = "💾 Atualizar Registro" if is_edicao else "💾 Salvar Novo Registro"
        submitted = st.form_submit_button(btn_label, type="primary", use_container_width=True)

    # ─── Processamento após submit ────────────────────────────────────────────
    if submitted:
        # BF% calculado por dobras (executa após submit, não em tempo real)
        bf_calculado = None
        if any(v > 0 for v in dobras_vals.values()):
            from calculos_fisio import calcular_bf_por_formula, sugerir_formula_dobras
            sugerida_id, sugerida_just = sugerir_formula_dobras(dobras_vals, sexo, bf_bio or 15.0)
            if formula_id != sugerida_id:
                st.caption(f"💡 Fórmula sugerida: **{FORMULAS_DOBRAS.get(sugerida_id,{}).get('nome','')}** — {sugerida_just}")
            bf_calculado = calcular_bf_por_formula(formula_id, dobras_vals, idade, sexo)
            if bf_calculado:
                peso_v = float(peso or 0)
                fm_  = round(peso_v * bf_calculado/100, 1) if peso_v > 0 else "—"
                ffm_ = round(peso_v * (1 - bf_calculado/100), 1) if peso_v > 0 else "—"
                st.success(f"✅ BF% ({formula_lbl}): **{bf_calculado}%** | FM: {fm_} kg | FFM: {ffm_} kg")

        # ICW/ECW ratio display
        if agua_intra > 0 and agua_extra > 0:
            ratio_icw = round(agua_intra / agua_extra, 3)
            cor_r = "🟢" if ratio_icw >= 1.90 else ("🟡" if ratio_icw >= 1.60 else "🔴")
            st.caption(f"{cor_r} ICW/ECW: **{ratio_icw}** (alvo show-day ≥ 1.90)")

        bf_calc_save = bf_calculado or (bf_calc_input if bf_calc_input > 0 else None)
        def _bf_auto():
            vals = [v for v in [bf_bio if bf_bio > 0 else None, bf_calc_save] if v]
            return round(sum(vals)/len(vals), 1) if vals else None
        bf_final_save = bf_final_input if bf_final_input > 0 else _bf_auto()

        payload = {
            "data":                str(data_reg),
            "hora_registro":       hora_reg or None,
            "peso":                float(peso)                  if peso > 0                 else None,
            "bf_bioimpedancia":    float(bf_bio)                if bf_bio > 0               else None,
            "bf_formula":          formula_id                   if bf_calc_save             else None,
            "bf_calculado":        float(bf_calc_save)          if bf_calc_save             else None,
            "bf_final":            float(bf_final_save)         if bf_final_save            else None,
            "massa_gordura":       float(massa_gordura)         if massa_gordura > 0        else None,
            "massa_livre_gordura": float(massa_livre_gordura)   if massa_livre_gordura > 0  else None,
            "agua_total":          float(agua_total)            if agua_total > 0           else None,
            "agua_intracelular":   float(agua_intra)            if agua_intra > 0           else None,
            "agua_extracelular":   float(agua_extra)            if agua_extra > 0           else None,
            "angulo_fase":         float(angulo_fase)           if angulo_fase > 0          else None,
            "resistencia":         float(resistencia)           if resistencia > 0          else None,
            "reactancia":          float(reactancia)            if reactancia > 0           else None,
            "carga_treino":        float(carga_treino)          if carga_treino > 0         else None,
            "vfc_noturna":         float(vfc_noturna)           if vfc_noturna > 0          else None,
            "sleep_score":         int(sleep_score)             if sleep_score > 0          else None,
            "recovery_time":       int(recovery_time)           if recovery_time > 0        else None,
            "fc_repouso":          int(fc_repouso)              if fc_repouso > 0           else None,
            **{k: (float(v) if v > 0 else None) for k, v in dobras_vals.items()},
            **{k: (float(v) if v > 0 else None) for k, v in circ_vals.items()},
            "notas": notas or None,
        }

        if is_edicao:
            atualizar_registro(str(editando["id"]), payload)
        else:
            salvar_novo_registro(payload)
        st.session_state["reg_editando"] = None
        st.session_state["_reg_pending"] = None
        st.rerun()

    # ─── Cancelar / Limpar — fora do form ────────────────────────────────────
    if is_edicao:
        col_cancel, col_clear, _ = st.columns([1, 1, 2])
        if col_cancel.button("✖ Cancelar edição", use_container_width=True, key="btn_cancel_edit"):
            st.session_state["reg_editando"] = None
            st.session_state["_reg_pending"] = None
            st.rerun()
        if col_clear.button("🔄 Limpar formulário", use_container_width=True, key="btn_clear"):
            st.session_state["reg_editando"] = None
            st.session_state["_reg_pending"] = None
            st.rerun()
    else:
        _, col_clear = st.columns([3, 1])
        if col_clear.button("🔄 Limpar formulário", use_container_width=True, key="btn_clear"):
            st.session_state["reg_editando"] = None
            st.session_state["_reg_pending"] = None
            st.rerun()



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


def tab_perfil(perfil: dict) -> None:
    """Aba de perfil do atleta + objetivos + zonas de FC."""
    st.header("👤 Perfil do Atleta")

    with st.form("form_perfil"):
        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("📋 Dados Pessoais")
            nome      = st.text_input("Nome", value=perfil.get("nome",""))
            dn_val    = datetime.strptime(str(perfil.get("data_nasc","1990-01-01")), "%Y-%m-%d").date()
            data_nasc = st.date_input("Data de nascimento", value=dn_val)
            sexo      = st.radio("Sexo biológico", ["Masculino","Feminino"],
                           index=0 if perfil.get("sexo","Masculino")=="Masculino" else 1,
                           horizontal=True)
            altura    = st.number_input("Altura (cm)", min_value=140, max_value=230,
                           value=int(float(perfil.get("altura",178))))
            anos_tr   = st.number_input("Anos de treino", min_value=0, max_value=40,
                           value=int(perfil.get("anos_treino",5)))

        with col2:
            st.subheader("🏆 Dados Competitivos")
            cat_opts = ["Mens Physique","Classic Physique","Bodybuilding Open",
                        "Bikini","Wellness","Physique Feminino"]
            cat_idx  = cat_opts.index(perfil.get("categoria","Mens Physique")) \
                       if perfil.get("categoria") in cat_opts else 0
            categoria = st.selectbox("Categoria alvo", cat_opts, index=cat_idx)
            uso_peds  = st.checkbox("Uso de PEDs / TRT", value=bool(perfil.get("uso_peds",False)))
            dc_val    = datetime.strptime(str(perfil.get("data_competicao",
                           str(date.today()+timedelta(days=120)))), "%Y-%m-%d").date()
            data_comp = st.date_input("Data da próxima competição", value=dc_val)
            vfc_base  = st.number_input("VFC Baseline (ms, média 7 dias)",
                           min_value=20.0, max_value=120.0,
                           value=float(perfil.get("vfc_baseline",60.0)), step=1.0)

        with col3:
            st.subheader("🎯 Objetivos no Palco")
            st.caption("Valores alvo para a data da competição. Usados no painel Atual vs Objetivo.")
            bf_alvo       = st.number_input("BF% alvo no palco",     min_value=2.0, max_value=20.0,
                                value=float(perfil.get("bf_alvo",5.0)), step=0.5)
            peso_alvo_m   = st.number_input("Peso alvo (kg)",         min_value=0.0, max_value=200.0,
                                value=float(perfil.get("peso_alvo") or 0), step=0.5,
                                help="Deixe 0 para calcular automaticamente como FFM ÷ (1 − BF%alvo).")
            cintura_alvo_m= st.number_input("Cintura alvo (cm)",      min_value=0.0, max_value=150.0,
                                value=float(perfil.get("cintura_alvo") or 0), step=0.5,
                                help="Deixe 0 para calcular pela Razão Áurea a partir dos ombros.")
            ombros_alvo_m = st.number_input("Ombros alvo (cm)",       min_value=0.0, max_value=200.0,
                                value=float(perfil.get("ombros_alvo") or 0), step=0.5,
                                help="Deixe 0 para calcular pela Razão Áurea a partir da cintura.")
            coxa_alvo_m   = st.number_input("Coxa alvo (cm)",         min_value=0.0, max_value=120.0,
                                value=float(perfil.get("coxa_alvo") or 0), step=0.5,
                                help="Deixe 0 para usar referência clássica (52–55% da altura).")

        idade_calc = calcular_idade(str(data_nasc))
        st.info(f"🎂 Idade calculada: **{idade_calc} anos**")

        if st.form_submit_button("💾 Salvar Perfil", type="primary", use_container_width=True):
            salvar_perfil({
                "nome": nome, "data_nasc": str(data_nasc), "sexo": sexo,
                "altura": float(altura), "anos_treino": int(anos_tr),
                "categoria": categoria, "uso_peds": bool(uso_peds),
                "data_competicao": str(data_comp), "vfc_baseline": float(vfc_base),
                "bf_alvo":       float(bf_alvo),
                "peso_alvo":     float(peso_alvo_m)    if peso_alvo_m > 0    else None,
                "cintura_alvo":  float(cintura_alvo_m) if cintura_alvo_m > 0 else None,
                "ombros_alvo":   float(ombros_alvo_m)  if ombros_alvo_m > 0  else None,
                "coxa_alvo":     float(coxa_alvo_m)    if coxa_alvo_m > 0    else None,
            })
            # Forçar reload do perfil diretamente do banco no próximo ciclo
            # (garante que o dashboard receba os valores persistidos, não o payload local)
            st.session_state.pop("perfil", None)
            st.rerun()

    # ── Zonas de FC ───────────────────────────────────────────────────────────
    st.divider()
    st.subheader("🫀 Zonas de Frequência Cardíaca")

    idade_p   = calcular_idade(str(perfil.get("data_nasc","1990-01-01")))
    ultimo    = carregar_ultimo_registro()
    fc_rep_db = int(ultimo.get("fc_repouso") or perfil.get("fc_repouso") or 55)

    zonas_kv = calcular_zonas_karvonen(idade_p, fc_rep_db)

    usar_manual = st.checkbox(
        "Tenho laudo de ergoespirometria — inserir zonas personalizadas",
        value=bool(perfil.get("zona1_min")), key="perfil_fc_manual"
    )

    nomes_z = [
        "Zona 1 — Recuperação Ativa",
        "Zona 2 — LISS / Fat-Burning",
        "Zona 3 — Aeróbio Moderado",
        "Zona 4 — Limiar Anaeróbio",
        "Zona 5 — HIIT / Máximo",
    ]
    emj_z = ["🔵","🟢","🟡","🟠","🔴"]

    if usar_manual:
        st.caption(f"FC repouso usada: **{fc_rep_db} bpm** (do último registro). Karvonen à direita para comparação.")
        h0,h1,h2,h3,h4 = st.columns([3,1,1,1,1])
        h0.markdown("**Zona**"); h1.markdown("**Manual min**"); h2.markdown("**Manual máx**")
        h3.markdown("**Karvonen min**"); h4.markdown("**Karvonen máx**")
        zonas_manual = {}
        for i, (nome_z, ez) in enumerate(zip(nomes_z, emj_z), 1):
            kv_mn, kv_mx = list(zonas_kv.values())[i-1]
            c0,c1,c2,c3,c4 = st.columns([3,1,1,1,1])
            c0.markdown(f"{ez} {nome_z}")
            mn = c1.number_input("min", min_value=0, step=1,
                value=int(perfil.get(f"zona{i}_min") or 0),
                key=f"pf_z{i}min", label_visibility="collapsed")
            mx = c2.number_input("máx", min_value=0, step=1,
                value=int(perfil.get(f"zona{i}_max") or 0),
                key=f"pf_z{i}max", label_visibility="collapsed")
            c3.markdown(f"<div style='text-align:center;padding-top:8px'>{kv_mn}</div>", unsafe_allow_html=True)
            c4.markdown(f"<div style='text-align:center;padding-top:8px'>{kv_mx}</div>", unsafe_allow_html=True)
            zonas_manual[f"zona{i}_min"] = mn
            zonas_manual[f"zona{i}_max"] = mx

        if st.button("💾 Salvar Zonas", type="secondary", key="btn_salvar_zonas"):
            salvar_perfil({**perfil, **zonas_manual})
            st.success("✅ Zonas salvas!")
    else:
        st.caption(f"Karvonen | FC repouso: **{fc_rep_db} bpm** | Idade: **{idade_p} anos**")
        for nome_z, ez, (mn, mx) in zip(nomes_z, emj_z, zonas_kv.values()):
            st.write(f"{ez} **{nome_z}:** {mn}–{mx} bpm")

    st.divider()
    st.caption("Karvonen: FC treino = [(FCmáx − FCrepouso) × intensidade%] + FCrepouso  \n"
               "FCmáx = 208 − 0.7 × idade (Tanaka et al., 2001). Para maior precisão, realize ergoespirometria.")



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
    if "perfil" not in st.session_state:
        st.session_state["perfil"] = carregar_perfil()
    perfil = st.session_state["perfil"]

    # Se não há perfil, usar dict vazio e abrir direto na aba Perfil com aviso
    perfil_vazio = not perfil
    if perfil_vazio:
        perfil = {}

    render_topbar(perfil)

    # Aviso de perfil incompleto — não bloqueia o app
    if perfil_vazio:
        st.warning("👤 **Complete seu perfil** na aba **👤 Perfil** para personalizar as recomendações. O app já está funcionando com valores padrão.")

    # ── Dados do último registro (fonte única para o app) ─────────────────────
    ultimo = carregar_ultimo_registro()
    df_historico = carregar_registros()  # compatibilidade para abas que ainda usam

    # Peso e BF% — vêm exclusivamente dos registros, sem fallback fixo
    peso_atual = float(ultimo.get("peso") or 0) or None
    bf_atual   = float(ultimo.get("bf_final") or ultimo.get("bf_calculado") or
                       ultimo.get("bf_bioimpedancia") or 0) or None

    # Dados de recuperação do último registro
    vfc_at   = float(ultimo.get("vfc_noturna")   or 0) or None
    sleep_sc = float(ultimo.get("sleep_score")   or 0) or None
    rec_time = float(ultimo.get("recovery_time") or 0) or None
    fc_rep   = float(ultimo.get("fc_repouso")    or 0) or None
    carga_tr = float(ultimo.get("carga_treino")  or 0) or None

    # Perfil
    sexo      = perfil.get("sexo","Masculino")
    categoria = perfil.get("categoria","Mens Physique")
    bf_alvo_p = float(perfil.get("bf_alvo",5.0))
    dc_str    = str(perfil.get("data_competicao", str(date.today()+timedelta(days=120))))
    data_comp = datetime.strptime(dc_str, "%Y-%m-%d").date()
    vfc_base  = float(perfil.get("vfc_baseline",0)) or None
    uso_peds  = bool(perfil.get("uso_peds",False))
    idade     = calcular_idade(str(perfil.get("data_nasc","1990-01-01")))
    anos_tr   = int(perfil.get("anos_treino",5))
    altura    = float(perfil.get("altura",178))

    # Objetivos manuais do perfil (None = calcular automaticamente no dashboard)
    peso_alvo_pf    = float(perfil.get("peso_alvo")    or 0) or None
    cintura_alvo_pf = float(perfil.get("cintura_alvo") or 0) or None
    ombros_alvo_pf  = float(perfil.get("ombros_alvo")  or 0) or None
    coxa_alvo_pf    = float(perfil.get("coxa_alvo")    or 0) or None

    # p = dict de parâmetros passados às abas
    p = {
        "peso_at": peso_atual, "bf_at": bf_atual,
        "vfc_at": vfc_at, "sleep_sc": sleep_sc, "rec_time": rec_time,
        "fc_rep": fc_rep, "carga_tr": carga_tr,
        "vfc_base": vfc_base,
        "sexo": sexo, "categoria": categoria, "bf_alvo": bf_alvo_p,
        "data_comp": data_comp, "uso_peds": uso_peds, "idade": idade,
        "anos_treino": anos_tr, "altura": altura,
        "data_reg": date.today(),
        # objetivos manuais do perfil
        "peso_alvo_pf":    peso_alvo_pf,
        "cintura_alvo_pf": cintura_alvo_pf,
        "ombros_alvo_pf":  ombros_alvo_pf,
        "coxa_alvo_pf":    coxa_alvo_pf,
    }

    # ── Fase e atleta ─────────────────────────────────────────────────────────
    bf_para_fase = bf_atual or 12.0  # só para sugerir fase, não travar
    fase, df_timeline, flags = sugerir_fase_e_timeline(
        date.today(), data_comp, bf_para_fase, sexo, df_historico)

    peso_para_calc = peso_atual or 80.0
    bf_para_calc   = bf_atual   or 12.0
    atleta = AtletaMetrics(
        categoria_alvo=categoria, peso=peso_para_calc, bf_atual=bf_para_calc,
        bf_alvo=bf_alvo_p, idade=idade, vfc_base=vfc_base or 60.0,
        vfc_atual=vfc_at or 0.0, sleep_score=int(sleep_sc or 0),
        recovery_time=int(rec_time or 0), fc_repouso=int(fc_rep or 55),
        carga_treino=carga_tr or 0.0, fase_sugerida=fase,
        uso_peds=uso_peds, estagnado_dias=0, data_competicao=data_comp,
        anos_treino=anos_tr,
    )
    df_dieta, motivo_dieta, alertas = calcular_macros_semana(atleta, df_historico, flags)
    dieta_hoje = df_dieta.iloc[date.today().weekday()]

    # ── Navegação ─────────────────────────────────────────────────────────────
    tabs = st.tabs([
        "🏠 Dashboard",
        "🗓️ Periodização",
        "🍽️ Nutrição",
        "🏋️ Treino",
        "🎯 Recuperação",
        "📁 Registros",
        "📊 Avaliação Semanal",
        "📈 Evolução",
        "👤 Perfil",
        "📚 Referências",
    ])

    with tabs[0]:  tab_dashboard(p, atleta, flags, fase, df_historico, df_timeline, dieta_hoje, df_dieta)
    with tabs[1]:  tab_periodizacao(fase, df_timeline, flags, p, atleta, df_historico)
    with tabs[2]:  tab_nutricao(fase, atleta, df_historico, flags, df_dieta, motivo_dieta, alertas, dieta_hoje, p)
    with tabs[3]:  tab_treino(fase, atleta, df_historico)
    with tabs[4]:  tab_recuperacao(atleta, df_historico, p)
    with tabs[5]:  tab_registros(p, atleta, perfil)
    with tabs[6]:  tab_avaliacao_semanal(atleta, df_historico, fase)
    with tabs[7]:  tab_evolucao(df_historico)
    with tabs[8]:  tab_perfil(perfil)
    with tabs[9]:  tab_referencias()

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if not sessao_ativa():
    render_tela_auth()
else:
    render_app()