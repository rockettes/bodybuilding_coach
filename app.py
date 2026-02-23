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

    # ── Métricas principais ───────────────────────────────────────────────────
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("Fase", fase)
    c2.metric("Dias p/ Show", f"{max(0,(p['data_comp']-date.today()).days)}d")
    taxa = f"{flags['taxa_perda_peso']:.2f}%/sem" if flags.get("taxa_perda_peso") else "—"
    c3.metric("Taxa Perda", taxa)
    peso_txt = f"{p['peso_at']} kg" if p['peso_at'] else "— (sem registro)"
    bf_txt   = f"{p['bf_at']}%"   if p['bf_at']   else "— (sem registro)"
    c4.metric("Peso Atual", peso_txt)
    c5.metric("BF Atual",   bf_txt)

    if flags.get("plato_metabolico"):
        st.error("🚨 **PLATÔ METABÓLICO** — Taxa < 0.5%/sem por 2 semanas. *(Peos et al., 2019)*")

    st.divider()

    col_rec, col_prop = st.columns([1, 1])

    with col_rec:
        # ── Status de recuperação ─────────────────────────────────────────────
        st.subheader("🎯 Status de Recuperação")
        (status_dia, acao_dia, motivo_dia, painel,
         acwr_val, acwr_status, cv_val, cv_status) = prescrever_treino_do_dia(atleta, df_hist)
        fn = st.error if "Severa" in status_dia else (st.warning if "Incompleta" in status_dia else st.success)
        fn(f"**{status_dia}**")
        st.info(f"**AÇÃO:** {acao_dia}")
        st.caption(f"*{motivo_dia}*")

        # ── Macros do dia ─────────────────────────────────────────────────────
        st.divider()
        st.subheader(f"🍽️ Alvo Nutricional — {dieta_hoje['Estratégia']}")
        mc1,mc2,mc3,mc4 = st.columns(4)
        mc1.metric("Calorias", f"{dieta_hoje['Calorias']} kcal")
        mc2.metric("Proteína", f"{dieta_hoje['Prot(g)']}g")
        mc3.metric("Carb", f"{dieta_hoje['Carb(g)']}g")
        mc4.metric("Gordura", f"{dieta_hoje['Gord(g)']}g")

    with col_prop:
        # ── Proporções Estéticas ──────────────────────────────────────────────
        st.subheader("📐 Proporções Estéticas")
        ultimo = carregar_ultimo_registro()
        medidas_d = {
            "cintura":  float(ultimo.get("cintura") or 0),
            "ombros":   float(ultimo.get("ombros")  or 0),
            "peito":    float(ultimo.get("peito")   or 0),
            "quadril":  float(ultimo.get("quadril") or 0),
            "biceps_d": float(ultimo.get("biceps_d") or 0),
            "coxa_d":   float(ultimo.get("coxa_d")  or 0),
        }
        altura_cm = float(p.get("altura") or 178.0)
        if any(v > 0 for v in medidas_d.values()):
            props = avaliar_proporcoes(p["categoria"], medidas_d, altura_cm)
            prop_info = PROPORCOES_CATEGORIA.get(p["categoria"], {})
            st.caption(f"*{prop_info.get('descricao','')}*")
            if "ombro_cintura" in props:
                r = props["ombro_cintura"]
                prog = min(r["atual"] / r["alvo"], 1.0) if r["alvo"] > 0 else 0
                st.progress(prog, text=f"Ombro/Cintura: {r['atual']:.3f} / φ {r['alvo']} — {r['status']}")
                st.caption(r["rec"])
            labels_prop = {
                "cintura":"Cintura","ombro_cintura":"Ombro/Cintura",
                "quadril_cintura":"Quadril/Cintura","peito_cintura":"Peito/Cintura",
            }
            for key, dados in props.items():
                label = labels_prop.get(key, key)
                alvo  = dados.get("alvo") or dados.get("alvo_max", "—")
                st.write(f"{dados['status']} **{label}** — Atual: `{dados.get('atual','—')}` | Alvo: `{alvo}`")
        else:
            st.info("Registre circunferências na aba **📁 Registros** para ver as proporções aqui.")


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
        fc_rep_z = int(p.get("fc_rep") or 55)
        if not p.get("fc_rep"):
            st.caption("⚠️ FC Repouso não registrada — usando 55 bpm como referência. Registre na aba 📁 Registros.")
        zonas = calcular_zonas_karvonen(int(p["idade"]), fc_rep_z)
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
    Aba unificada de todos os registros. Um registro = uma linha com data/hora + quaisquer campos.
    Campos vazios gravam NULL. Sem auto-preenchimento de valores — só auto-preencher
    do último registro via botão por grupo.
    """
    st.header("📁 Registros")

    # ── Estado da sessão ──────────────────────────────────────────────────────
    # reg_editando: dict com o registro selecionado para edição (None = novo)
    if "reg_editando" not in st.session_state:
        st.session_state["reg_editando"] = None

    # ── Histórico (sempre visível no topo) ────────────────────────────────────
    st.subheader("📋 Histórico de Registros")
    df_all = carregar_todos_registros()

    sel_id = None  # ID do registro selecionado

    if df_all.empty:
        st.info("Nenhum registro encontrado. Crie o primeiro abaixo.")
    else:
        # Colunas resumidas para a tabela
        cols_resumo = ["data","hora_registro","peso","bf_final","vfc_noturna",
                       "sleep_score","recovery_time","carga_treino","angulo_fase","notas"]
        cols_ok = [c for c in cols_resumo if c in df_all.columns]
        df_disp = df_all[["id"] + cols_ok].copy() if "id" in df_all.columns else df_all[cols_ok].copy()

        ev = st.dataframe(
            df_disp.drop(columns=["id"], errors="ignore"),
            on_select="rerun", selection_mode="single-row",
            use_container_width=True, hide_index=True,
        )

        if ev.selection.rows:
            row_idx = ev.selection.rows[0]
            row = df_all.iloc[row_idx].to_dict()
            sel_id = str(row.get("id",""))
            st.session_state["reg_editando"] = row
            st.caption(f"✏️ Registro **{row.get('data','')} {row.get('hora_registro','')}** selecionado — edite abaixo e salve, ou delete.")
        else:
            # Se nenhuma linha selecionada, limpar edição anterior
            if st.session_state.get("_last_sel_id") and st.session_state["reg_editando"]:
                st.session_state["reg_editando"] = None
            st.session_state["_last_sel_id"] = sel_id

    st.divider()

    # ── Modo: novo ou edição ──────────────────────────────────────────────────
    editando = st.session_state["reg_editando"]
    is_edicao = editando is not None

    if is_edicao:
        st.subheader("✏️ Editando Registro")
        col_info, col_del = st.columns([4, 1])
        with col_info:
            st.info(f"Editando: **{editando.get('data','')} {editando.get('hora_registro','')}**")
        with col_del:
            if st.button("🗑️ Deletar este registro", type="secondary", use_container_width=True, key="btn_del"):
                deletar_registro_unificado(str(editando["id"]))
                st.session_state["reg_editando"] = None
                st.rerun()
    else:
        st.subheader("➕ Novo Registro")

    # Último registro para botão auto-preencher
    ultimo = carregar_ultimo_registro()

    def _v(campo: str, default=None):
        """Retorna valor do registro em edição, ou None para novo."""
        if is_edicao:
            v = editando.get(campo)
            return v if v is not None else default
        return default

    def _f(v, t=float):
        """Converte para tipo seguro; None se vazio."""
        try:
            r = t(v)
            return r if r != 0 else None
        except:
            return None

    # ── DATA E HORA (auto no novo, editável) ─────────────────────────────────
    st.markdown("#### 📅 Data e Hora")
    now = datetime.now()
    col_d, col_h = st.columns(2)
    with col_d:
        data_reg = st.date_input("Data",
            value=datetime.strptime(str(_v("data", now.strftime("%Y-%m-%d"))), "%Y-%m-%d").date(),
            key="reg_data")
    with col_h:
        hora_default = _v("hora_registro", now.strftime("%H:%M"))
        hora_reg = st.text_input("Hora (HH:MM)", value=str(hora_default) if hora_default else now.strftime("%H:%M"), key="reg_hora")

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO 1 — COMPOSIÇÃO CORPORAL
    # ════════════════════════════════════════════════════════════════════════
    st.divider()

    col_g1_hdr, col_g1_btn = st.columns([4, 1])
    with col_g1_hdr:
        st.markdown("#### ⚖️ Composição Corporal")
        st.caption("Dados diretos da balança de bioimpedância ou calculados.")
    with col_g1_btn:
        if st.button("📋 Preencher do último registro", key="fill_comp", use_container_width=True):
            for k in ["peso","bf_bioimpedancia","bf_formula","bf_calculado","bf_final",
                      "massa_gordura","massa_livre_gordura",
                      "agua_total","agua_intracelular","agua_extracelular",
                      "angulo_fase","resistencia","reactancia"]:
                st.session_state[f"reg_{k}"] = ultimo.get(k) or ""

    cc1, cc2, cc3 = st.columns(3)
    with cc1:
        peso = st.number_input("Peso (kg)", min_value=0.0, max_value=300.0, step=0.05,
            value=_f(_v("peso")) or 0.0, format="%.2f", key="reg_peso")
        massa_gordura = st.number_input("Massa de Gordura FM (kg)", min_value=0.0, step=0.1,
            value=_f(_v("massa_gordura")) or 0.0, key="reg_massa_gordura")
        massa_livre_gordura = st.number_input("Massa Livre de Gordura FFM (kg)", min_value=0.0, step=0.1,
            value=_f(_v("massa_livre_gordura")) or 0.0, key="reg_massa_livre_gordura")
    with cc2:
        bf_bio = st.number_input("BF% Bioimpedância", min_value=0.0, max_value=60.0, step=0.1,
            value=_f(_v("bf_bioimpedancia")) or 0.0, key="reg_bf_bioimpedancia",
            help="Valor direto do aparelho de bioimpedância.")

        # Selecionar fórmula de dobras
        sexo  = p.get("sexo","Masculino")
        idade = p.get("idade", 30)
        opcoes_f = [(fid, fi["nome"]) for fid, fi in __import__("calculos_fisio").FORMULAS_DOBRAS.items()
                    if (fi["campos_masc"] if sexo=="Masculino" else fi["campos_fem"])]
        labels_f = [v for _,v in opcoes_f]; ids_f = [k for k,_ in opcoes_f]
        cur_formula = _v("bf_formula", "jp7")
        idx_f = ids_f.index(cur_formula) if cur_formula in ids_f else 0
        formula_lbl = st.selectbox("Fórmula das dobras", labels_f, index=idx_f, key="reg_bf_formula_sel")
        formula_id  = ids_f[labels_f.index(formula_lbl)]

        bf_calc_input = st.number_input("BF% por Dobras (calculado)", min_value=0.0, max_value=60.0, step=0.1,
            value=_f(_v("bf_calculado")) or 0.0, key="reg_bf_calculado",
            help="Calculado automaticamente ao salvar se dobras estiverem preenchidas.")
    with cc3:
        bf_final_input = st.number_input("BF% Final (usado nos cálculos)", min_value=0.0, max_value=60.0, step=0.1,
            value=_f(_v("bf_final")) or 0.0, key="reg_bf_final",
            help="Deixe 0 para calcular automaticamente como média Bio + Dobras.")

        st.markdown("**BIA Avançada**")
        st.caption("Resistência (R), Reactância (Xc) e Ângulo de Fase — exportados por aparelhos avançados de BIA (InBody, Tanita série profissional).")
        resistencia = st.number_input("Resistência R (Ω)", min_value=0.0, step=1.0,
            value=_f(_v("resistencia")) or 0.0, key="reg_resistencia")
        reactancia  = st.number_input("Reactância Xc (Ω)", min_value=0.0, step=0.5,
            value=_f(_v("reactancia")) or 0.0, key="reg_reactancia")
        angulo_fase = st.number_input("Ângulo de Fase (°)", min_value=0.0, max_value=20.0, step=0.1,
            value=_f(_v("angulo_fase")) or 0.0, key="reg_angulo_fase",
            help="PhA = arctan(Xc/R) × 180°/π. Atletas de elite: 7–12°. Bodybuilders show-day: 9.6–11.2°. *(Kyle et al., 2005; Ribas et al., 2022)*")

    # Água corporal
    st.markdown("**Água Corporal**")
    st.caption("TBW = ICW + ECW. Na Peak Week o objetivo é aumentar ICW e reduzir ECW → ICW/ECW ≥ 1.90. *(Ribas et al., 2022 — PMC8880471)*")
    cw1, cw2, cw3 = st.columns(3)
    agua_total = cw1.number_input("Água Total TBW (L)", min_value=0.0, step=0.1,
        value=_f(_v("agua_total")) or 0.0, key="reg_agua_total")
    agua_intra = cw2.number_input("Água Intracelular ICW (L)", min_value=0.0, step=0.1,
        value=_f(_v("agua_intracelular")) or 0.0, key="reg_agua_intracelular")
    agua_extra = cw3.number_input("Água Extracelular ECW (L)", min_value=0.0, step=0.1,
        value=_f(_v("agua_extracelular")) or 0.0, key="reg_agua_extracelular")
    if agua_intra > 0 and agua_extra > 0:
        ratio_icw = round(agua_intra / agua_extra, 3)
        cor_r = "🟢" if ratio_icw >= 1.90 else ("🟡" if ratio_icw >= 1.60 else "🔴")
        st.caption(f"{cor_r} ICW/ECW ratio: **{ratio_icw}** (alvo show-day: ≥ 1.90)")

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO 2 — DADOS DE RECUPERAÇÃO
    # ════════════════════════════════════════════════════════════════════════
    st.divider()
    col_g2_hdr, col_g2_btn = st.columns([4, 1])
    with col_g2_hdr:
        st.markdown("#### 🎯 Dados de Recuperação (Garmin / Wearable)")
    with col_g2_btn:
        if st.button("📋 Preencher do último", key="fill_rec", use_container_width=True):
            for k in ["carga_treino","vfc_noturna","sleep_score","recovery_time","fc_repouso"]:
                st.session_state[f"reg_{k}"] = ultimo.get(k) or ""

    rc1, rc2, rc3 = st.columns(3)
    with rc1:
        carga_treino  = st.number_input("Volume Load (kg×reps)", min_value=0.0, step=10.0,
            value=_f(_v("carga_treino")) or 0.0, key="reg_carga_treino")
        vfc_noturna   = st.number_input("VFC Noturna (ms)", min_value=0.0, step=1.0,
            value=_f(_v("vfc_noturna")) or 0.0, key="reg_vfc_noturna")
    with rc2:
        sleep_score   = st.number_input("Sleep Score (0–100)", min_value=0, max_value=100, step=1,
            value=int(_v("sleep_score") or 0), key="reg_sleep_score")
        recovery_time = st.number_input("Recovery Time (h)", min_value=0, step=1,
            value=int(_v("recovery_time") or 0), key="reg_recovery_time")
    with rc3:
        fc_repouso = st.number_input("FC Repouso (bpm)", min_value=0, step=1,
            value=int(_v("fc_repouso") or 0), key="reg_fc_repouso")

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO 3 — DOBRAS CUTÂNEAS
    # ════════════════════════════════════════════════════════════════════════
    st.divider()
    col_g3_hdr, col_g3_btn = st.columns([4, 1])
    with col_g3_hdr:
        st.markdown("#### 🔬 Dobras Cutâneas (mm)")
        st.caption("Plicômetro, lado direito do corpo. Todos os campos opcionais.")
    with col_g3_btn:
        if st.button("📋 Preencher do último", key="fill_dob", use_container_width=True):
            for k in ["dobra_peitoral","dobra_axilar","dobra_tricipital","dobra_subescapular",
                      "dobra_abdominal","dobra_suprailiaca","dobra_coxa","dobra_bicipital"]:
                st.session_state[f"reg_{k}"] = ultimo.get(k) or ""

    db1, db2, db3, db4 = st.columns(4)
    dobras_vals = {}
    campos_dobras = [
        ("dobra_peitoral","Peitoral",db1), ("dobra_axilar","Axilar",db2),
        ("dobra_tricipital","Tricipital",db3), ("dobra_subescapular","Subescapular",db4),
        ("dobra_abdominal","Abdominal",db1), ("dobra_suprailiaca","Suprailiaca",db2),
        ("dobra_coxa","Coxa",db3), ("dobra_bicipital","Bíceps (Durnin)",db4),
    ]
    for campo, label, col in campos_dobras:
        with col:
            v = dobras_vals[campo] = st.number_input(label, min_value=0.0, step=0.5,
                value=_f(_v(campo)) or 0.0, key=f"reg_{campo}")

    # Calcular BF% pelas dobras automaticamente
    bf_calculado = None
    if any(v > 0 for v in dobras_vals.values()):
        from calculos_fisio import calcular_bf_por_formula, sugerir_formula_dobras, FORMULAS_DOBRAS
        sugerida_id, sugerida_just = sugerir_formula_dobras(dobras_vals, sexo, bf_bio or 15.0)
        if formula_id != sugerida_id:
            st.caption(f"💡 Sugestão: {FORMULAS_DOBRAS.get(sugerida_id,{}).get('nome','')} — {sugerida_just}")
        bf_calculado = calcular_bf_por_formula(formula_id, dobras_vals, idade, sexo)
        if bf_calculado:
            st.success(f"✅ BF% calculado ({formula_lbl}): **{bf_calculado}%**  "
                       f"| FM: {round((peso or 0)*(bf_calculado/100),1)}kg "
                       f"| FFM: {round((peso or 0)*(1-bf_calculado/100),1)}kg")

    # ════════════════════════════════════════════════════════════════════════
    # GRUPO 4 — CIRCUNFERÊNCIAS
    # ════════════════════════════════════════════════════════════════════════
    st.divider()
    col_g4_hdr, col_g4_btn = st.columns([4, 1])
    with col_g4_hdr:
        st.markdown("#### 📐 Circunferências (cm)")
    with col_g4_btn:
        if st.button("📋 Preencher do último", key="fill_circ", use_container_width=True):
            for k in ["cintura","ombros","peito","quadril","biceps_d","coxa_d","panturrilha_d","pescoco"]:
                st.session_state[f"reg_{k}"] = ultimo.get(k) or ""

    ci1, ci2, ci3, ci4 = st.columns(4)
    campos_circ = [
        ("cintura","Cintura",ci1), ("ombros","Ombros",ci2),
        ("peito","Peito",ci3), ("quadril","Quadril",ci4),
        ("biceps_d","Bíceps D",ci1), ("coxa_d","Coxa D",ci2),
        ("panturrilha_d","Panturrilha D",ci3), ("pescoco","Pescoço",ci4),
    ]
    circ_vals = {}
    for campo, label, col in campos_circ:
        with col:
            circ_vals[campo] = st.number_input(label, min_value=0.0, step=0.5,
                value=_f(_v(campo)) or 0.0, key=f"reg_{campo}")

    # ── Notas ─────────────────────────────────────────────────────────────────
    st.divider()
    notas = st.text_area("📝 Notas", value=str(_v("notas","") or ""), height=70, key="reg_notas")

    # ── Botões de ação ────────────────────────────────────────────────────────
    st.divider()
    btn_label = "💾 Atualizar Registro" if is_edicao else "💾 Salvar Novo Registro"

    # Calcular bf_final automático se não informado
    def _calc_bf_final():
        vals = [v for v in [bf_bio or None, bf_calculado] if v]
        if not vals: return None
        return round(sum(vals)/len(vals), 1)

    bf_final_save = (bf_final_input if bf_final_input > 0
                     else (_calc_bf_final() or None))
    bf_calc_save  = bf_calculado or (bf_calc_input if bf_calc_input > 0 else None)

    payload = {
        "data":  str(data_reg),
        "hora_registro": hora_reg or None,
        # Composição
        "peso":                float(peso)                 if peso > 0 else None,
        "bf_bioimpedancia":    float(bf_bio)               if bf_bio > 0 else None,
        "bf_formula":          formula_id                  if bf_calc_save else None,
        "bf_calculado":        float(bf_calc_save)         if bf_calc_save else None,
        "bf_final":            float(bf_final_save)        if bf_final_save else None,
        "massa_gordura":       float(massa_gordura)        if massa_gordura > 0 else None,
        "massa_livre_gordura": float(massa_livre_gordura)  if massa_livre_gordura > 0 else None,
        # BIA avançada
        "agua_total":          float(agua_total)           if agua_total > 0 else None,
        "agua_intracelular":   float(agua_intra)           if agua_intra > 0 else None,
        "agua_extracelular":   float(agua_extra)           if agua_extra > 0 else None,
        "angulo_fase":         float(angulo_fase)          if angulo_fase > 0 else None,
        "resistencia":         float(resistencia)          if resistencia > 0 else None,
        "reactancia":          float(reactancia)           if reactancia > 0 else None,
        # Recuperação
        "carga_treino":        float(carga_treino)         if carga_treino > 0 else None,
        "vfc_noturna":         float(vfc_noturna)          if vfc_noturna > 0 else None,
        "sleep_score":         int(sleep_score)            if sleep_score > 0 else None,
        "recovery_time":       int(recovery_time)          if recovery_time > 0 else None,
        "fc_repouso":          int(fc_repouso)             if fc_repouso > 0 else None,
        # Dobras
        **{k: (float(v) if v > 0 else None) for k, v in dobras_vals.items()},
        # Circunferências
        **{k: (float(v) if v > 0 else None) for k, v in circ_vals.items()},
        "notas": notas or None,
    }

    col_save, col_cancel = st.columns([2, 1])
    with col_save:
        if st.button(btn_label, type="primary", use_container_width=True, key="btn_salvar_reg"):
            if is_edicao:
                atualizar_registro(str(editando["id"]), payload)
            else:
                salvar_novo_registro(payload)
            st.session_state["reg_editando"] = None
            st.rerun()
    with col_cancel:
        if is_edicao:
            if st.button("✖ Cancelar edição", use_container_width=True, key="btn_cancel_edit"):
                st.session_state["reg_editando"] = None
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
    """Aba de perfil do atleta + zonas de FC (Karvonen lado a lado com manual)."""
    st.header("👤 Perfil do Atleta")

    # ── Dados do perfil ───────────────────────────────────────────────────────
    with st.form("form_perfil"):
        col1, col2 = st.columns(2)
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
            cat_opts  = ["Mens Physique","Classic Physique","Bodybuilding Open",
                         "Bikini","Wellness","Physique Feminino"]
            cat_idx   = cat_opts.index(perfil.get("categoria","Mens Physique"))                         if perfil.get("categoria") in cat_opts else 0
            categoria = st.selectbox("Categoria alvo", cat_opts, index=cat_idx)
            uso_peds  = st.checkbox("Uso de PEDs / TRT", value=bool(perfil.get("uso_peds",False)))
            bf_alvo   = st.number_input("% BF alvo no palco", min_value=2.0, max_value=20.0,
                           value=float(perfil.get("bf_alvo",5.0)), step=0.5)
            dc_val    = datetime.strptime(str(perfil.get("data_competicao",
                           str(date.today()+timedelta(days=120)))), "%Y-%m-%d").date()
            data_comp = st.date_input("Data da próxima competição", value=dc_val)
            vfc_base  = st.number_input("VFC Baseline (média 7 dias, ms)",
                           min_value=20.0, max_value=120.0,
                           value=float(perfil.get("vfc_baseline",60.0)), step=1.0)

        idade_calc = calcular_idade(str(data_nasc))
        st.info(f"🎂 Idade calculada: **{idade_calc} anos**")

        if st.form_submit_button("💾 Salvar Perfil", type="primary", use_container_width=True):
            salvar_perfil({
                "nome": nome, "data_nasc": str(data_nasc), "sexo": sexo,
                "altura": float(altura), "anos_treino": int(anos_tr),
                "categoria": categoria, "uso_peds": bool(uso_peds),
                "bf_alvo": float(bf_alvo), "data_competicao": str(data_comp),
                "vfc_baseline": float(vfc_base),
            })
            st.session_state["perfil"] = None  # forçar reload
            st.rerun()

    # ── Zonas de FC ───────────────────────────────────────────────────────────
    st.divider()
    st.subheader("🫀 Zonas de Frequência Cardíaca")

    idade_p   = calcular_idade(str(perfil.get("data_nasc","1990-01-01")))
    ultimo    = carregar_ultimo_registro()
    fc_rep_db = int(ultimo.get("fc_repouso") or perfil.get("fc_repouso") or 55)

    # Karvonen (sempre calculado)
    zonas_kv = calcular_zonas_karvonen(idade_p, fc_rep_db)

    usar_manual = st.checkbox(
        "Tenho laudo de ergoespirometria — quero inserir zonas personalizadas",
        value=bool(perfil.get("zona1_min")), key="perfil_fc_manual"
    )

    nomes_z = [
        "Zona 1 — Recuperação Ativa",
        "Zona 2 — LISS / Fat-Burning",
        "Zona 3 — Aeróbio Moderado",
        "Zona 4 — Limiar Anaeróbio",
        "Zona 5 — HIIT / Máximo",
    ]
    emj = ["🔵","🟢","🟡","🟠","🔴"]

    if usar_manual:
        st.caption("Preencha as zonas do laudo. Valores Karvonen mostrados ao lado para comparação.")
        # Cabeçalho
        h0, h1, h2, h3, h4 = st.columns([3, 1, 1, 1, 1])
        h0.markdown("**Zona**")
        h1.markdown("**Manual min**")
        h2.markdown("**Manual máx**")
        h3.markdown("**Karvonen min**")
        h4.markdown("**Karvonen máx**")

        zonas_manual = {}
        for i, (nome_z, emj_z) in enumerate(zip(nomes_z, emj), 1):
            kv_mn, kv_mx = list(zonas_kv.values())[i-1]
            c0, c1, c2, c3, c4 = st.columns([3, 1, 1, 1, 1])
            c0.markdown(f"{emj_z} {nome_z}")
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

        if st.button("💾 Salvar Zonas Personalizadas", type="secondary", key="btn_salvar_zonas"):
            dados_z = {**perfil, **zonas_manual}
            salvar_perfil(dados_z)
            st.success("✅ Zonas salvas!")
    else:
        st.caption(f"Cálculo pela fórmula de Karvonen | FC repouso: {fc_rep_db} bpm | Idade: {idade_p} anos")
        for nome_z, emj_z, (mn, mx) in zip(nomes_z, emj, zonas_kv.values()):
            st.write(f"{emj_z} **{nome_z}:** {mn}–{mx} bpm")

    st.divider()
    st.caption("""
**Karvonen:** FC treino = [(FCmáx − FCrepouso) × intensidade%] + FCrepouso
FCmáx estimada pela fórmula de Tanaka et al. (2001): 208 − 0.7 × idade.
Para maior precisão, realize teste ergoespirométrico.
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
    if "perfil" not in st.session_state:
        st.session_state["perfil"] = carregar_perfil()
    perfil = st.session_state["perfil"]
    if not perfil:
        render_onboarding()
        return

    render_topbar(perfil)

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
        "💊 Suplementação",
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
    with tabs[7]:  tab_suplementacao(atleta)
    with tabs[8]:  tab_evolucao(df_historico)
    with tabs[9]:  tab_perfil(perfil)
    with tabs[10]: tab_referencias()

# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

if not sessao_ativa():
    render_tela_auth()
else:
    render_app()