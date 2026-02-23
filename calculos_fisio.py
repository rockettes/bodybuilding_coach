"""
calculos_fisio.py — Motor científico do Pro Coach IA
──────────────────────────────────────────────────────
v3.0 — Adicionado:
  - Motor de otimização multi-objetivo (Pareto)
  - Metas semanais por fase com avaliação automática
  - Proporções estéticas por categoria (Razão Áurea, Steve Reeves)
  - Cálculo de BF% por dobras cutâneas (Jackson-Pollock 7 dobras)
  - Termogênese adaptativa (Trexler et al., 2014)
  - ACWR e CV-VFC integrados
  - Zonas FC manuais (ergoespirometria) ou automáticas (Karvonen)
"""

import math
import random
from datetime import datetime, date, timedelta
from typing import Dict, Tuple, List, Optional, Any
from dataclasses import dataclass, field
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# DATACLASS PRINCIPAL
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AtletaMetrics:
    categoria_alvo: str
    peso: float
    bf_atual: float
    bf_alvo: float
    idade: int
    vfc_base: float
    vfc_atual: float
    sleep_score: int
    recovery_time: int
    fc_repouso: int
    carga_treino: float
    fase_sugerida: str
    uso_peds: bool
    estagnado_dias: int
    data_competicao: date
    anos_treino: int = 5

    @property
    def lbm(self) -> float:
        return self.peso * (1 - self.bf_atual / 100)

    @property
    def fm(self) -> float:
        return self.peso * (self.bf_atual / 100)


# ─────────────────────────────────────────────────────────────────────────────
# PROPORÇÕES ESTÉTICAS POR CATEGORIA
# ─────────────────────────────────────────────────────────────────────────────

PHI = 1.618

PROPORCOES_CATEGORIA = {
    "Mens Physique": {
        "ombro_cintura_ratio_alvo": PHI,
        "ombro_cintura_minimo": 1.50,
        "cintura_max_pct_altura": 0.44,
        "peito_cintura_ratio": 1.30,
        "braco_pct_cintura": 0.50,
        "descricao": "V-taper máximo. Ombros ≥ 1.618× cintura (Razão Áurea). Cintura ≤ 44% altura.",
    },
    "Classic Physique": {
        "ombro_cintura_ratio_alvo": PHI,
        "ombro_cintura_minimo": 1.55,
        "cintura_max_pct_altura": 0.46,
        "peito_cintura_ratio": 1.35,
        "braco_pct_cintura": 0.52,
        "descricao": "Proporção clássica Steve Reeves. Maior massa que Mens Physique, mesma razão áurea.",
    },
    "Bodybuilding Open": {
        "ombro_cintura_ratio_alvo": 1.55,
        "ombro_cintura_minimo": 1.45,
        "cintura_max_pct_altura": 0.48,
        "peito_cintura_ratio": 1.40,
        "braco_pct_cintura": 0.58,
        "descricao": "Massa máxima. Cintura controlada é crucial mesmo com volume extremo.",
    },
    "Bikini": {
        "quadril_cintura_ratio_alvo": 1.40,
        "quadril_cintura_minimo": 1.30,
        "cintura_max_pct_altura": 0.42,
        "descricao": "Proporção quadril/cintura ≥ 1.40. Curvas definidas, cintura fina.",
    },
    "Wellness": {
        "quadril_cintura_ratio_alvo": 1.55,
        "quadril_cintura_minimo": 1.45,
        "cintura_max_pct_altura": 0.43,
        "coxa_cintura_ratio": 0.70,
        "descricao": "Glúteos e coxas desenvolvidos. Quadril/cintura ≥ 1.55.",
    },
    "Physique Feminino": {
        "ombro_cintura_ratio_alvo": 1.45,
        "ombro_cintura_minimo": 1.35,
        "cintura_max_pct_altura": 0.42,
        "descricao": "V-taper feminino. Ombros definidos, cintura fina.",
    },
}


def avaliar_proporcoes(categoria: str, medidas: dict, altura_cm: float) -> dict:
    """Avalia proporções atuais vs. alvos da categoria. Retorna dict com status e gaps."""
    prop = PROPORCOES_CATEGORIA.get(categoria, {})
    resultado = {}

    cintura = medidas.get("cintura", 0) or 0
    ombros  = medidas.get("ombros",  0) or 0
    quadril = medidas.get("quadril", 0) or 0
    peito   = medidas.get("peito",   0) or 0
    biceps  = medidas.get("biceps_d",0) or 0
    coxa    = medidas.get("coxa_d",  0) or 0

    if cintura > 0 and altura_cm > 0:
        cintura_max = prop.get("cintura_max_pct_altura", 0.46) * altura_cm
        resultado["cintura"] = {
            "atual": cintura,
            "alvo_max": round(cintura_max, 1),
            "status": "✅" if cintura <= cintura_max else "❌",
            "gap": round(cintura - cintura_max, 1),
            "rec": f"Reduzir {round(cintura - cintura_max, 1)}cm" if cintura > cintura_max else "✅ Dentro do alvo",
        }

    if cintura > 0 and ombros > 0:
        ratio_atual = ombros / cintura
        ratio_alvo  = prop.get("ombro_cintura_ratio_alvo", PHI)
        ratio_min   = prop.get("ombro_cintura_minimo", 1.50)
        ombros_alvo = round(cintura * ratio_alvo, 1)
        resultado["ombro_cintura"] = {
            "atual": round(ratio_atual, 3),
            "alvo": ratio_alvo,
            "minimo": ratio_min,
            "ombros_necessarios": ombros_alvo,
            "status": "✅" if ratio_atual >= ratio_alvo else ("🟡" if ratio_atual >= ratio_min else "❌"),
            "gap_ratio": round(ratio_alvo - ratio_atual, 3),
            "rec": (f"Aumentar ombros {round(ombros_alvo - ombros, 1)}cm ou reduzir cintura"
                    if ratio_atual < ratio_alvo else "✅ Razão Áurea atingida!"),
        }

    if cintura > 0 and quadril > 0:
        ratio_atual = quadril / cintura
        ratio_alvo  = prop.get("quadril_cintura_ratio_alvo", 1.40)
        ratio_min   = prop.get("quadril_cintura_minimo", 1.30)
        resultado["quadril_cintura"] = {
            "atual": round(ratio_atual, 3),
            "alvo": ratio_alvo,
            "status": "✅" if ratio_atual >= ratio_alvo else ("🟡" if ratio_atual >= ratio_min else "❌"),
            "rec": "Desenvolver glúteos/quadril" if ratio_atual < ratio_alvo else "✅ Proporção atingida",
        }

    if cintura > 0 and peito > 0:
        ratio_atual = peito / cintura
        ratio_alvo  = prop.get("peito_cintura_ratio", 1.30)
        resultado["peito_cintura"] = {
            "atual": round(ratio_atual, 3),
            "alvo": ratio_alvo,
            "status": "✅" if ratio_atual >= ratio_alvo else "🟡",
            "rec": "Priorizar peito e costas" if ratio_atual < ratio_alvo else "✅ Ok",
        }

    if cintura > 0 and biceps > 0:
        ratio_atual = biceps / cintura
        ratio_alvo  = prop.get("braco_pct_cintura", 0.50)
        resultado["braco_cintura"] = {
            "atual": round(ratio_atual, 3),
            "alvo": ratio_alvo,
            "status": "✅" if ratio_atual >= ratio_alvo else "🟡",
            "rec": f"Alvo braço: {round(cintura * ratio_alvo, 1)}cm",
        }

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# DOBRAS CUTÂNEAS — Múltiplas fórmulas
# ─────────────────────────────────────────────────────────────────────────────

FORMULAS_DOBRAS = {
    "jp7": {
        "nome": "Jackson-Pollock 7 dobras",
        "descricao": "Protocolo completo com 7 pontos. Maior precisão (±3.5%). Recomendada para bodybuilders.",
        "campos_masc": ["dobra_peitoral","dobra_axilar","dobra_tricipital",
                        "dobra_subescapular","dobra_abdominal","dobra_suprailiaca","dobra_coxa"],
        "campos_fem":  ["dobra_peitoral","dobra_axilar","dobra_tricipital",
                        "dobra_subescapular","dobra_abdominal","dobra_suprailiaca","dobra_coxa"],
        "referencia": "Jackson & Pollock, 1978",
    },
    "jp3_masc": {
        "nome": "Jackson-Pollock 3 dobras (Masculino)",
        "descricao": "Versão rápida para homens: peitoral + abdominal + coxa. Precisão ±4%.",
        "campos_masc": ["dobra_peitoral","dobra_abdominal","dobra_coxa"],
        "campos_fem":  [],
        "referencia": "Jackson & Pollock, 1978",
    },
    "jp3_fem": {
        "nome": "Jackson-Pollock 3 dobras (Feminino)",
        "descricao": "Versão rápida para mulheres: tricipital + suprailiaca + coxa. Precisão ±4%.",
        "campos_masc": [],
        "campos_fem":  ["dobra_tricipital","dobra_suprailiaca","dobra_coxa"],
        "referencia": "Jackson et al., 1980",
    },
    "durnin": {
        "nome": "Durnin-Womersley 4 dobras",
        "descricao": "Bíceps + tríceps + subescapular + suprailiaca. Boa para BF% elevado (>20%).",
        "campos_masc": ["dobra_bicipital","dobra_tricipital","dobra_subescapular","dobra_suprailiaca"],
        "campos_fem":  ["dobra_bicipital","dobra_tricipital","dobra_subescapular","dobra_suprailiaca"],
        "referencia": "Durnin & Womersley, 1974",
    },
}


def _dc_para_bf(dc: float) -> float:
    """Converte densidade corporal em % BF pela equação de Siri (1956)."""
    bf = (495 / dc) - 450
    return round(max(2.0, min(60.0, bf)), 1)


def calcular_bf_jp7(dobras: dict, idade: int, sexo: str) -> Optional[float]:
    """Jackson & Pollock (1978) — 7 dobras."""
    campos = ["dobra_peitoral","dobra_axilar","dobra_tricipital",
              "dobra_subescapular","dobra_abdominal","dobra_suprailiaca","dobra_coxa"]
    vals = [dobras.get(c) for c in campos]
    if any(v is None or float(v) <= 0 for v in vals):
        return None
    soma = sum(float(v) for v in vals)
    if sexo == "Masculino":
        dc = 1.112 - (0.00043499*soma) + (0.00000055*soma**2) - (0.00028826*idade)
    else:
        dc = 1.097 - (0.00046971*soma) + (0.00000056*soma**2) - (0.00012828*idade)
    return _dc_para_bf(dc)


def calcular_bf_jp3_masc(dobras: dict, idade: int) -> Optional[float]:
    """Jackson & Pollock (1978) — 3 dobras masculino: peitoral + abdominal + coxa."""
    campos = ["dobra_peitoral","dobra_abdominal","dobra_coxa"]
    vals = [dobras.get(c) for c in campos]
    if any(v is None or float(v) <= 0 for v in vals):
        return None
    soma = sum(float(v) for v in vals)
    dc = 1.10938 - (0.0008267*soma) + (0.0000016*soma**2) - (0.0002574*idade)
    return _dc_para_bf(dc)


def calcular_bf_jp3_fem(dobras: dict, idade: int) -> Optional[float]:
    """Jackson et al. (1980) — 3 dobras feminino: tricipital + suprailiaca + coxa."""
    campos = ["dobra_tricipital","dobra_suprailiaca","dobra_coxa"]
    vals = [dobras.get(c) for c in campos]
    if any(v is None or float(v) <= 0 for v in vals):
        return None
    soma = sum(float(v) for v in vals)
    dc = 1.0994921 - (0.0009929*soma) + (0.0000023*soma**2) - (0.0001392*idade)
    return _dc_para_bf(dc)


def calcular_bf_durnin(dobras: dict, idade: int, sexo: str) -> Optional[float]:
    """Durnin & Womersley (1974) — 4 dobras: bíceps + tríceps + subescapular + suprailiaca."""
    campos = ["dobra_bicipital","dobra_tricipital","dobra_subescapular","dobra_suprailiaca"]
    vals = [dobras.get(c) for c in campos]
    if any(v is None or float(v) <= 0 for v in vals):
        return None
    log_soma = math.log10(sum(float(v) for v in vals))

    # Coeficientes por sexo e faixa etária
    if sexo == "Masculino":
        if idade < 30:    c, m = 1.1620, 0.0630
        elif idade < 40:  c, m = 1.1631, 0.0632
        elif idade < 50:  c, m = 1.1422, 0.0544
        else:             c, m = 1.1620, 0.0700
    else:
        if idade < 30:    c, m = 1.1549, 0.0678
        elif idade < 40:  c, m = 1.1599, 0.0717
        elif idade < 50:  c, m = 1.1423, 0.0632
        else:             c, m = 1.1333, 0.0612
    dc = c - m * log_soma
    return _dc_para_bf(dc)


# Alias para compatibilidade
def calcular_bf_jackson_pollock7(dobras: dict, idade: int, sexo: str) -> Optional[float]:
    return calcular_bf_jp7(dobras, idade, sexo)


def calcular_bf_por_formula(
    formula_id: str, dobras: dict, idade: int, sexo: str
) -> Optional[float]:
    """Dispatcha para a fórmula correta baseado no formula_id."""
    if formula_id == "jp7":
        return calcular_bf_jp7(dobras, idade, sexo)
    elif formula_id == "jp3_masc":
        return calcular_bf_jp3_masc(dobras, idade)
    elif formula_id == "jp3_fem":
        return calcular_bf_jp3_fem(dobras, idade)
    elif formula_id == "durnin":
        return calcular_bf_durnin(dobras, idade, sexo)
    return None


def sugerir_formula_dobras(dobras: dict, sexo: str, bf_estimado: float) -> Tuple[str, str]:
    """
    Sugere a melhor fórmula de dobras para o caso específico.
    Retorna (formula_id, justificativa).
    """
    tem_7  = all(dobras.get(c, 0) > 0 for c in
                 ["dobra_peitoral","dobra_axilar","dobra_tricipital",
                  "dobra_subescapular","dobra_abdominal","dobra_suprailiaca","dobra_coxa"])
    tem_4  = all(dobras.get(c, 0) > 0 for c in
                 ["dobra_bicipital","dobra_tricipital","dobra_subescapular","dobra_suprailiaca"])
    tem_3m = all(dobras.get(c, 0) > 0 for c in
                 ["dobra_peitoral","dobra_abdominal","dobra_coxa"])
    tem_3f = all(dobras.get(c, 0) > 0 for c in
                 ["dobra_tricipital","dobra_suprailiaca","dobra_coxa"])

    # BF% acima de 20% → Durnin mais preciso
    if bf_estimado > 20 and tem_4:
        return "durnin", "BF% estimado acima de 20% → Durnin-Womersley é mais precisa nesta faixa."

    # 7 dobras disponíveis → sempre preferível para bodybuilders
    if tem_7:
        return "jp7", "7 dobras disponíveis → JP7 é o protocolo de maior precisão para atletas de fisiculturismo."

    # 4 dobras disponíveis
    if tem_4:
        return "durnin", "4 dobras (bíceps+tríceps+subescapular+suprailiaca) disponíveis → Durnin-Womersley."

    # 3 dobras por sexo
    if sexo == "Masculino" and tem_3m:
        return "jp3_masc", "3 dobras masculinas (peitoral+abdominal+coxa) disponíveis → JP3 masculino."
    if sexo == "Feminino" and tem_3f:
        return "jp3_fem", "3 dobras femininas (tricipital+suprailiaca+coxa) disponíveis → JP3 feminino."

    return "jp7", "Preencha as dobras acima para calcular o BF%."


def calcular_lbm_fm_por_dobras(peso: float, dobras: dict, idade: int, sexo: str):
    bf = calcular_bf_jp7(dobras, idade, sexo)
    if bf is None:
        return None, None, None
    return bf, round(peso*(1-bf/100), 2), round(peso*(bf/100), 2)


# ─────────────────────────────────────────────────────────────────────────────
# METAS SEMANAIS
# ─────────────────────────────────────────────────────────────────────────────

def calcular_metas_semana(atleta: AtletaMetrics) -> dict:
    """
    Gera metas semanais baseadas na fase e experiência.
    *(Iraki et al., 2019; Helms et al., 2014; Garthe et al., 2013)*
    """
    peso  = atleta.peso
    anos  = atleta.anos_treino
    peds  = atleta.uso_peds

    if atleta.fase_sugerida == "Bulking":
        if anos <= 2:    taxa = 0.005
        elif anos <= 4:  taxa = 0.0035
        else:            taxa = 0.0025
        taxa *= (1.3 if peds else 1.0)

        g_peso = round(peso * taxa, 2)
        g_lbm  = round(g_peso * 0.65, 2)
        g_fm   = round(g_peso * 0.35, 2)
        g_fm_max = round(g_peso * 0.40, 2)
        bf_max = round(atleta.bf_atual + 0.15, 1)

        return {
            "fase": "Bulking",
            "ganho_peso_min":  round(g_peso * 0.5, 2),
            "ganho_peso_alvo": g_peso,
            "ganho_peso_max":  round(g_peso * 1.5, 2),
            "ganho_lbm_alvo":  g_lbm,
            "ganho_fm_alvo":   g_fm,
            "ganho_fm_max":    g_fm_max,
            "bf_max":          bf_max,
            "variacao_volume_load": "+2.5%",
            "referencia": "Iraki et al., 2019 / Garthe et al., 2013",
            "descricao": (
                f"Alvo: +{g_peso}kg/sem ({g_lbm}kg LBM + {g_fm}kg FM). "
                f"FM máximo: +{g_fm_max}kg/sem. BF% máximo: {bf_max}%."
            ),
        }

    elif atleta.fase_sugerida in ["Cutting","Pre-Contest (Cutting)"]:
        p_alvo = round(peso * 0.007, 2)
        p_min  = round(peso * 0.005, 2)
        p_max  = round(peso * 0.010, 2)
        lbm_max = round(p_alvo * 0.25, 2)

        return {
            "fase": "Cutting",
            "perda_peso_min":  p_min,
            "perda_peso_alvo": p_alvo,
            "perda_peso_max":  p_max,
            "perda_lbm_max":   lbm_max,
            "bf_alvo_semana":  round(atleta.bf_atual - 0.35, 1),
            "variacao_volume_load": "0% (manter)",
            "referencia": "Helms et al., 2014",
            "descricao": (
                f"Alvo: -{p_alvo}kg/sem (intervalo: -{p_min} a -{p_max}kg). "
                f"Perda LBM tolerável: <{lbm_max}kg/sem."
            ),
        }

    elif atleta.fase_sugerida == "Peak Week":
        return {
            "fase": "Peak Week",
            "perda_peso_alvo": round(peso * 0.01, 2),
            "bf_alvo_semana": round(atleta.bf_alvo, 1),
            "variacao_volume_load": "-40%",
            "referencia": "Chappell et al., 2018",
            "descricao": "Depleção + supercompensação. Foco em definição visual.",
        }

    else:
        return {
            "fase": "Recomposição",
            "ganho_lbm_alvo": round(atleta.lbm * 0.002, 2),
            "perda_fm_alvo":  round(atleta.fm  * 0.005, 2),
            "bf_alvo_semana": round(atleta.bf_atual - 0.15, 1),
            "variacao_volume_load": "+1%",
            "referencia": "Barakat et al., 2020",
            "descricao": "Ganho lento de LBM com perda simultânea de FM.",
        }


# ─────────────────────────────────────────────────────────────────────────────
# AVALIAÇÃO SEMANAL + MOTOR MULTI-OBJETIVO
# ─────────────────────────────────────────────────────────────────────────────

def avaliar_resultados_semana(df_historico: pd.DataFrame, metas: dict, fase: str) -> dict:
    """
    Compara última semana com as metas e retorna diagnóstico + ajustes.
    Detecta conflitos multi-objetivo e solicita priorização ao atleta.
    """
    if df_historico.empty or len(df_historico) < 7:
        return {"status": "insuficiente", "msg": "Mínimo 7 registros para avaliação semanal."}

    df = df_historico.sort_values("Data").copy()
    df["Peso"]    = pd.to_numeric(df["Peso"],    errors="coerce")
    df["BF_Atual"] = pd.to_numeric(df["BF_Atual"], errors="coerce")

    p_ini  = df.iloc[-7]["Peso"]
    p_fim  = df.iloc[-1]["Peso"]
    bf_ini = df.iloc[-7]["BF_Atual"]
    bf_fim = df.iloc[-1]["BF_Atual"]

    delta_peso = round(p_fim - p_ini, 2)
    delta_bf   = round(bf_fim - bf_ini, 2)
    lbm_ini    = p_ini * (1 - bf_ini/100)
    lbm_fim    = p_fim * (1 - bf_fim/100)
    fm_ini     = p_ini * (bf_ini/100)
    fm_fim     = p_fim * (bf_fim/100)
    delta_lbm  = round(lbm_fim - lbm_ini, 2)
    delta_fm   = round(fm_fim  - fm_ini,  2)

    resultado = {
        "delta_peso": delta_peso,
        "delta_lbm":  delta_lbm,
        "delta_fm":   delta_fm,
        "delta_bf":   delta_bf,
        "ajustes":    [],
        "conflitos":  [],
        "status":     "ok",
    }

    if fase == "Bulking":
        alvo_min  = metas.get("ganho_peso_min", 0)
        alvo_max  = metas.get("ganho_peso_max", 99)
        fm_max    = metas.get("ganho_fm_max", 99)
        bf_max    = metas.get("bf_max", 99)

        if delta_peso < alvo_min:
            resultado["ajustes"].append({
                "objetivo": "Ganho de Massa",
                "problema": f"Ganho insuficiente ({delta_peso:+.2f}kg vs. mín +{alvo_min}kg)",
                "acao": "Aumentar calorias +200kcal/dia",
                "delta_calorias": +200, "prioridade": 2,
            })
        elif delta_peso > alvo_max:
            resultado["ajustes"].append({
                "objetivo": "Controle de Gordura",
                "problema": f"Ganho excessivo ({delta_peso:+.2f}kg vs. máx +{alvo_max}kg)",
                "acao": "Reduzir calorias -200kcal/dia",
                "delta_calorias": -200, "prioridade": 1,
            })

        if delta_fm > fm_max:
            resultado["ajustes"].append({
                "objetivo": "Controle de Gordura",
                "problema": f"Gordura excessiva (+{delta_fm:.2f}kg vs. máx +{fm_max:.2f}kg)",
                "acao": "Reduzir calorias -150kcal/dia",
                "delta_calorias": -150, "prioridade": 1,
            })

        if bf_fim > bf_max:
            resultado["ajustes"].append({
                "objetivo": "BF% Crítico",
                "problema": f"BF% acima do limite ({bf_fim:.1f}% vs. máx {bf_max:.1f}%)",
                "acao": "Mini-cut de 2 semanas",
                "delta_calorias": -400, "prioridade": 0,
            })

    elif fase in ["Cutting","Pre-Contest (Cutting)"]:
        p_min     = metas.get("perda_peso_min", 0)
        p_max     = metas.get("perda_peso_max", 99)
        lbm_max   = metas.get("perda_lbm_max", 99)

        if delta_peso > -p_min:  # perdeu menos que o mínimo
            resultado["ajustes"].append({
                "objetivo": "Taxa de Perda",
                "problema": f"Perda insuficiente ({delta_peso:+.2f}kg vs. alvo ≤-{p_min}kg)",
                "acao": "Aumentar déficit -200kcal/dia ou +cardio 20min",
                "delta_calorias": -200, "prioridade": 2,
            })
        elif delta_peso < -p_max:  # perdeu mais que o máximo
            resultado["ajustes"].append({
                "objetivo": "Retenção de LBM",
                "problema": f"Perda excessiva ({delta_peso:+.2f}kg vs. máx -{p_max}kg)",
                "acao": "Reduzir déficit +200kcal/dia",
                "delta_calorias": +200, "prioridade": 1,
            })

        if delta_lbm < -lbm_max:
            resultado["ajustes"].append({
                "objetivo": "Preservação de LBM",
                "problema": f"Perda de LBM excessiva ({delta_lbm:.2f}kg vs. máx -{lbm_max:.2f}kg)",
                "acao": "Aumentar proteína +0.3g/kg e reduzir déficit +150kcal",
                "delta_calorias": +150, "prioridade": 0,
            })

    # Detectar conflito multi-objetivo
    tem_subir  = any(a["delta_calorias"] > 0 for a in resultado["ajustes"])
    tem_descer = any(a["delta_calorias"] < 0 for a in resultado["ajustes"])

    if tem_subir and tem_descer:
        if fase == "Bulking":
            resultado["conflitos"].append({
                "descricao": (
                    "⚠️ **CONFLITO MULTI-OBJETIVO:** O ganho de peso está abaixo do alvo "
                    "(sugere +calorias), mas o ganho de gordura/BF% está acima do limite "
                    "(sugere -calorias). Escolha uma prioridade:"
                ),
                "opcoes": [
                    {"label": "🏋️ Priorizar Ganho de Massa",
                     "descricao": "+200kcal/dia — aceita mais gordura no curto prazo",
                     "delta_calorias": +200},
                    {"label": "⚖️ Priorizar Controle de Gordura",
                     "descricao": "-150kcal/dia — crescimento mais lento, menos gordura",
                     "delta_calorias": -150},
                    {"label": "✂️ Mini-cut 2 semanas",
                     "descricao": "Pausa no bulking para resetar BF%, depois retoma com melhor partição",
                     "delta_calorias": -500},
                ],
            })
        else:
            resultado["conflitos"].append({
                "descricao": (
                    "⚠️ **CONFLITO MULTI-OBJETIVO:** A taxa de perda de peso está baixa "
                    "(sugere mais déficit), mas a perda de LBM está acima do tolerável "
                    "(sugere menos déficit). Escolha uma prioridade:"
                ),
                "opcoes": [
                    {"label": "🔥 Priorizar Perda de Gordura",
                     "descricao": "-200kcal/dia — aceita alguma perda de LBM",
                     "delta_calorias": -200},
                    {"label": "💪 Priorizar Preservação de LBM",
                     "descricao": "+150kcal/dia — perda mais lenta mas preserva músculo",
                     "delta_calorias": +150},
                ],
            })
        resultado["status"] = "conflito"

    # Ordenar por prioridade
    resultado["ajustes"].sort(key=lambda x: x.get("prioridade", 99))

    if not resultado["ajustes"] and not resultado["conflitos"]:
        resultado["status"] = "on_track"
        resultado["msg"] = "✅ Dentro das metas. Manter protocolo atual."

    return resultado


# ─────────────────────────────────────────────────────────────────────────────
# FASE E TIMELINE
# ─────────────────────────────────────────────────────────────────────────────

def sugerir_fase_e_timeline(
    data_atual, data_competicao, bf_atual: float, sexo: str, df_historico: pd.DataFrame
) -> Tuple[str, pd.DataFrame, dict]:
    fases_timeline = []
    flags: dict = {}

    # Histórico
    if not df_historico.empty and "Fase_Historica" in df_historico.columns:
        df_h = df_historico.dropna(subset=["Fase_Historica","Data"]).sort_values("Data")
        if not df_h.empty:
            start = df_h.iloc[0]["Data"]
            cur   = df_h.iloc[0]["Fase_Historica"]
            for _, row in df_h.iterrows():
                if row["Fase_Historica"] != cur:
                    fases_timeline.append({"Fase":f"Histórico: {cur}","Inicio":start,"Fim":row["Data"]})
                    start = row["Data"]
                    cur   = row["Fase_Historica"]
            fases_timeline.append({"Fase":f"Histórico: {cur}","Inicio":start,
                                    "Fim":data_atual.strftime("%Y-%m-%d") if hasattr(data_atual,"strftime") else str(data_atual)})

    # Taxa de perda e platô
    if not df_historico.empty and len(df_historico) >= 14:
        df_s = df_historico.sort_values("Data").copy()
        df_s["Peso"] = pd.to_numeric(df_s["Peso"], errors="coerce")
        p_ini = df_s.iloc[-14]["Peso"]
        p_fim = df_s.iloc[-1]["Peso"]
        taxa  = ((p_ini - p_fim) / p_ini) * 100 / 2
        flags["taxa_perda_peso"]  = round(taxa, 3)
        flags["plato_metabolico"] = taxa < 0.5 and taxa > -0.1

    # Projeção
    dias_totais = (data_competicao - data_atual).days if hasattr(data_competicao,"days") else (data_competicao - data_atual).days
    limite_bf   = 15.0 if sexo == "Masculino" else 22.0

    if dias_totais <= 0:
        fase_atual = "Pós-Campeonato / Transição"
        from datetime import timedelta
        fases_timeline.append({"Fase":"Projeção: "+fase_atual,"Inicio":data_atual,
                                "Fim":data_atual+timedelta(days=30)})
        return fase_atual, pd.DataFrame(fases_timeline), flags

    from datetime import timedelta
    inicio_peak = data_competicao - timedelta(days=7)
    inicio_cut  = inicio_peak   - timedelta(days=112)

    if data_atual < inicio_cut:
        fase_off = "Bulking" if bf_atual < limite_bf else "Recomposição Corporal"
        fases_timeline += [
            {"Fase":"Projeção: "+fase_off,    "Inicio":data_atual,  "Fim":inicio_cut},
            {"Fase":"Projeção: Cutting",       "Inicio":inicio_cut,  "Fim":inicio_peak},
            {"Fase":"Projeção: Peak Week",     "Inicio":inicio_peak, "Fim":data_competicao},
        ]
        fase_atual = fase_off
    elif data_atual < inicio_peak:
        fases_timeline += [
            {"Fase":"Projeção: Cutting",   "Inicio":data_atual,  "Fim":inicio_peak},
            {"Fase":"Projeção: Peak Week", "Inicio":inicio_peak, "Fim":data_competicao},
        ]
        fase_atual = "Cutting"
    else:
        fases_timeline.append({"Fase":"Projeção: Peak Week","Inicio":data_atual,"Fim":data_competicao})
        fase_atual = "Peak Week"

    return fase_atual, pd.DataFrame(fases_timeline), flags


# ─────────────────────────────────────────────────────────────────────────────
# TMB + TERMOGÊNESE ADAPTATIVA
# ─────────────────────────────────────────────────────────────────────────────

def calcular_tmb_katch_mcardle(peso: float, bf: float) -> float:
    lbm = peso * (1 - bf/100)
    return 370 + (21.6 * lbm)

def calcular_get(tmb: float, nivel: float = 1.55) -> float:
    return tmb * nivel

def aplicar_termogenese_adaptativa(calorias: float, semanas_deficit: int) -> float:
    """Reduz ~15kcal/semana após 4 semanas em déficit. *(Trexler et al., 2014)*"""
    if semanas_deficit <= 4:
        return calorias
    return calorias - min((semanas_deficit - 4) * 15, 200)


# ─────────────────────────────────────────────────────────────────────────────
# MACROS SEMANAIS
# ─────────────────────────────────────────────────────────────────────────────

def calcular_macros_semana(
    atleta: AtletaMetrics, df_historico: pd.DataFrame, flags: dict
) -> Tuple[pd.DataFrame, str, dict]:
    tmb  = calcular_tmb_katch_mcardle(atleta.peso, atleta.bf_atual)
    get  = calcular_get(tmb)
    alertas: dict = {}

    semanas_deficit = 0
    if not df_historico.empty and atleta.fase_sugerida in ["Cutting","Pre-Contest (Cutting)"]:
        if "Fase_Historica" in df_historico.columns:
            df_cut = df_historico[df_historico["Fase_Historica"] == "Cutting"]
            semanas_deficit = len(df_cut) // 7

    dias = ["Segunda","Terça","Quarta","Quinta","Sexta","Sábado","Domingo"]
    plano = []

    if atleta.fase_sugerida == "Bulking":
        surplus  = 500 if atleta.uso_peds else 300
        calorias = get + surplus
        prot = atleta.lbm * (2.8 if atleta.uso_peds else 2.2)
        gord = atleta.peso * 1.0
        carb = max(50, (calorias - prot*4 - gord*9) / 4)
        for d in dias:
            plano.append({"Dia":d,"Estratégia":"Superávit Base",
                "Calorias":round(calorias),"Carb(g)":round(carb),
                "Prot(g)":round(prot),"Gord(g)":round(gord)})
        motivo = (f"**Bulking** — Superávit {surplus}kcal. "
                  f"Prot: {round(prot)}g/dia ({2.8 if atleta.uso_peds else 2.2:.1f}g/kg LBM). "
                  f"*(Iraki et al., 2019)*")

    elif atleta.fase_sugerida in ["Cutting","Pre-Contest (Cutting)"]:
        cal_base = get - 500
        if atleta.estagnado_dias >= 7:
            cal_base -= 200
            alertas["platô"] = "⚠️ Platô: déficit aumentado -200kcal."
        cal_base = aplicar_termogenese_adaptativa(cal_base, semanas_deficit)
        if semanas_deficit > 4:
            adj = min((semanas_deficit-4)*15, 200)
            alertas["termogenese"] = f"⚠️ Termogênese adaptativa: -{adj}kcal aplicados. *(Trexler et al., 2014)*"
        prot = atleta.lbm * 3.1
        gord = atleta.peso * 0.7
        carb_low = max(30, (cal_base - prot*4 - gord*9) / 4)
        carb_ref = carb_low + (get - cal_base) / 4
        for i, d in enumerate(dias):
            if i < 5:
                plano.append({"Dia":d,"Estratégia":"Low Carb (Déficit)",
                    "Calorias":round(cal_base),"Carb(g)":round(carb_low),
                    "Prot(g)":round(prot),"Gord(g)":round(gord)})
            else:
                plano.append({"Dia":d,"Estratégia":"Refeed (Manutenção)",
                    "Calorias":round(get),"Carb(g)":round(carb_ref),
                    "Prot(g)":round(prot),"Gord(g)":round(gord)})
        motivo = (f"**Cutting 5:2** — Déficit {round(get-cal_base)}kcal + Refeed fim de semana. "
                  f"Prot: {round(prot)}g (3.1g/kg LBM). *(Helms et al., 2014)*")

    elif atleta.fase_sugerida == "Peak Week":
        prot_d = atleta.peso * 3.0; gord_d = atleta.peso * 0.8; carb_d = 50
        cal_d  = prot_d*4 + gord_d*9 + carb_d*4
        prot_u = atleta.peso * 2.0; gord_u = atleta.peso * 0.4; carb_u = atleta.peso * 8.0
        cal_u  = prot_u*4 + gord_u*9 + carb_u*4
        estrats = ["Depleção Extrema","Depleção Extrema","Depleção Extrema",
                   "Carb-Up (Loading)","Carb-Up (Loading)","Spillover Check","Dia do Show"]
        for i, d in enumerate(dias):
            if i < 3:
                plano.append({"Dia":d,"Estratégia":estrats[i],"Calorias":round(cal_d),
                    "Carb(g)":round(carb_d),"Prot(g)":round(prot_d),"Gord(g)":round(gord_d)})
            elif i < 5:
                plano.append({"Dia":d,"Estratégia":estrats[i],"Calorias":round(cal_u),
                    "Carb(g)":round(carb_u),"Prot(g)":round(prot_u),"Gord(g)":round(gord_u)})
            else:
                carb_m = max(0, (get - prot_d*4 - gord_u*9) / 4)
                plano.append({"Dia":d,"Estratégia":estrats[i],"Calorias":round(get),
                    "Carb(g)":round(carb_m),"Prot(g)":round(prot_d),"Gord(g)":round(gord_u)})
        motivo = "**Peak Week** — Depleção (Dias 1-3) + Supercompensação 8g/kg CHO (Dias 4-5). *(Chappell et al., 2018)*"

    else:
        calorias = get - 200
        prot = atleta.lbm * 2.5
        gord = atleta.peso * 0.9
        carb = max(30, (calorias - prot*4 - gord*9) / 4)
        for d in dias:
            plano.append({"Dia":d,"Estratégia":"Leve Déficit",
                "Calorias":round(calorias),"Carb(g)":round(carb),
                "Prot(g)":round(prot),"Gord(g)":round(gord)})
        motivo = f"**Recomposição** — Déficit leve 200kcal. Prot: {round(prot)}g. *(Barakat et al., 2020)*"

    alertas["get_base"] = f"TMB: {round(tmb)}kcal | GET estimado: {round(get)}kcal"
    return pd.DataFrame(plano), motivo, alertas


# ─────────────────────────────────────────────────────────────────────────────
# ZONAS DE FC
# ─────────────────────────────────────────────────────────────────────────────

def calcular_zonas_karvonen(idade: int, fc_repouso) -> Dict[str, Tuple[int,int]]:
    fc_repouso = int(fc_repouso or 55)  # fallback 55 bpm se None/0
    fc_max = 208 - (0.7 * idade)
    fcr    = fc_max - fc_repouso
    return {
        "Zona 1 (Recuperação Ativa)":  (int(fcr*.50+fc_repouso), int(fcr*.60+fc_repouso)),
        "Zona 2 (LISS / Fat-Burning)": (int(fcr*.60+fc_repouso), int(fcr*.70+fc_repouso)),
        "Zona 3 (Aeróbio Moderado)":   (int(fcr*.70+fc_repouso), int(fcr*.80+fc_repouso)),
        "Zona 4 (Limiar Anaeróbio)":   (int(fcr*.80+fc_repouso), int(fcr*.90+fc_repouso)),
        "Zona 5 (HIIT / Máximo)":      (int(fcr*.90+fc_repouso), int(fc_max)),
    }

def zonas_fc_manuais(dados: dict) -> Dict[str, Tuple[int,int]]:
    """Zonas definidas por ergoespirometria — precedem Karvonen se presentes."""
    nomes = ["Zona 1 (Recuperação Ativa)","Zona 2 (LISS / Fat-Burning)",
             "Zona 3 (Aeróbio Moderado)","Zona 4 (Limiar Anaeróbio)","Zona 5 (HIIT / Máximo)"]
    zonas = {}
    for i, nome in enumerate(nomes, 1):
        mn = dados.get(f"zona{i}_min"); mx = dados.get(f"zona{i}_max")
        if mn and mx and float(mn) > 0 and float(mx) > 0:
            zonas[nome] = (int(float(mn)), int(float(mx)))
    return zonas if len(zonas) >= 3 else {}


# ─────────────────────────────────────────────────────────────────────────────
# ACWR e CV-VFC
# ─────────────────────────────────────────────────────────────────────────────

def calcular_acwr(df_historico: pd.DataFrame) -> Tuple[Optional[float], str]:
    if df_historico.empty or len(df_historico) < 7:
        return None, "Dados insuficientes (mín. 7 registros)."
    df = df_historico.sort_values("Data").copy()
    df["Carga_Treino"] = pd.to_numeric(df["Carga_Treino"], errors="coerce").fillna(0)
    aguda   = df["Carga_Treino"].iloc[-7:].mean()
    cronica = df["Carga_Treino"].iloc[-min(28,len(df)):].mean()
    if cronica == 0:
        return None, "Carga crônica zerada."
    acwr = round(aguda / cronica, 3)
    if acwr < 0.8:    s = "🔵 Subtreino — aumente volume gradualmente"
    elif acwr <= 1.3: s = "🟢 Zona ótima (0.8–1.3)"
    elif acwr <= 1.5: s = "🟡 Atenção — monitore fadiga"
    else:             s = "🔴 Alto risco — reduza volume imediatamente"
    return acwr, s


def calcular_cv_vfc(df_historico: pd.DataFrame) -> Tuple[Optional[float], str]:
    if df_historico.empty or len(df_historico) < 7:
        return None, "Dados insuficientes (mín. 7 registros)."
    df = df_historico.sort_values("Data").copy()
    df["VFC_Atual"] = pd.to_numeric(df["VFC_Atual"], errors="coerce")
    vfc7 = df["VFC_Atual"].dropna().iloc[-7:]
    if len(vfc7) < 7 or vfc7.mean() == 0:
        return None, "VFC insuficiente."
    cv = round((vfc7.std() / vfc7.mean()) * 100, 1)
    if cv <= 7:    s = "🟢 VFC estável — recuperação adequada"
    elif cv <= 10: s = "🟡 VFC variável — atenção ao volume"
    else:          s = "🔴 VFC instável — sobrecarga ou doença?"
    return cv, s


# ─────────────────────────────────────────────────────────────────────────────
# PRESCRIÇÃO DO DIA
# ─────────────────────────────────────────────────────────────────────────────

def prescrever_treino_do_dia(atleta: AtletaMetrics, df_historico: pd.DataFrame):
    queda = ((atleta.vfc_base - atleta.vfc_atual) / atleta.vfc_base * 100
             if atleta.vfc_base > 0 else 0)
    txt_vfc = f"Queda {queda:.1f}%" if queda > 0 else f"Aumento {abs(queda):.1f}%"
    painel  = (f"⚙️ VFC: **{txt_vfc}** | Sleep: **{atleta.sleep_score}** | "
               f"Recovery: **{atleta.recovery_time}h** | FC: **{atleta.fc_repouso}bpm**")

    acwr_val, acwr_s = calcular_acwr(df_historico)
    cv_val,   cv_s   = calcular_cv_vfc(df_historico)

    pts = 0
    if queda >= 20:                pts += 3
    elif queda >= 10:              pts += 2
    if atleta.sleep_score < 50:    pts += 2
    elif atleta.sleep_score < 70:  pts += 1
    if atleta.recovery_time >= 48: pts += 2
    elif atleta.recovery_time >= 36: pts += 1
    if acwr_val and acwr_val > 1.5: pts += 1
    if cv_val  and cv_val  > 10:    pts += 1

    if pts >= 5:
        return ("🔴 Fadiga Severa","DESCANSO TOTAL",
                f"Fadiga {pts}/10. Supressão parassimpática. *(Flatt & Esco, 2016)*",
                painel, acwr_val, acwr_s, cv_val, cv_s)
    elif pts >= 3:
        return ("🟡 Recuperação Incompleta","CARDIO ZONA 2 — 30-45min",
                f"Fadiga {pts}/10. SNC em recuperação. *(Jamieson, 2009)*",
                painel, acwr_val, acwr_s, cv_val, cv_s)
    else:
        return ("🟢 Totalmente Recuperado","TREINO DE MUSCULAÇÃO",
                f"Fadiga {pts}/10. Prontidão total. *(Kiviniemi et al., 2007)*",
                painel, acwr_val, acwr_s, cv_val, cv_s)


# ─────────────────────────────────────────────────────────────────────────────
# TREINO SEMANAL
# ─────────────────────────────────────────────────────────────────────────────

def gerar_treino_semanal(atleta: AtletaMetrics, exercicios_db: List[Dict]) -> Tuple[pd.DataFrame, str]:
    fase = atleta.fase_sugerida
    if fase == "Bulking":
        series, reps, descanso, rir = 4, 10, 90, "1-2"
        motivo = "**Bulking** — Volume MAV (4×10), RIR 1-2. *(Israetel et al., 2019)*"
    elif fase in ["Cutting","Pre-Contest (Cutting)"]:
        series, reps, descanso, rir = 3, 8, 120, "0-1"
        motivo = "**Cutting** — Volume MEV-MAV (3×8), RIR 0-1. *(Helms et al., 2014)*"
    elif fase == "Peak Week":
        series, reps, descanso, rir = 2, 15, 60, "3-4"
        motivo = "**Peak Week** — Volume MEV (2×15), RIR 3-4. *(Chappell et al., 2018)*"
    else:
        series, reps, descanso, rir = 3, 12, 75, "1-2"
        motivo = "**Recomposição** — Volume intermediário (3×12). *(Barakat et al., 2020)*"

    divisao = {
        "A — Peito / Ombro / Tríceps": [
            "Peitoral","Peitoral Superior","Peitoral Inferior",
            "Deltóide Anterior","Deltóide Lateral","Tríceps","Tríceps (Cabeça Longa)"],
        "B — Costas / Bíceps / Posterior": [
            "Latíssimo do Dorso","Dorsal (Espessura)","Deltóide Posterior",
            "Trapézio Superior","Bíceps","Bíceps (Cabeça Longa)","Braquiorradial"],
        "C — Pernas / Panturrilha / Core": [
            "Quadríceps","Isquiotibiais","Glúteo Máximo","Glúteo Médio",
            "Gastrocnêmio","Sóleo","Reto Abdominal","Oblíquos"],
    }

    plano = []
    for treino, musculos in divisao.items():
        disp = [e for e in exercicios_db if e.get("musculo_principal_ativado") in musculos]
        random.shuffle(disp)
        for ex in disp[:6]:
            plano.append({"Treino":treino,"Exercício":ex["nome"],"Séries":series,
                "Reps":reps,"RIR":rir,"Descanso(s)":descanso,
                "Músculo":ex.get("musculo_principal_ativado","")})

    return pd.DataFrame(plano), motivo


# ─────────────────────────────────────────────────────────────────────────────
# SUPLEMENTAÇÃO
# ─────────────────────────────────────────────────────────────────────────────

def recomendar_suplementos(atleta: AtletaMetrics) -> pd.DataFrame:
    base = [
        {"Suplemento":"Creatina Monoidratada","Dose":"3–5g/dia","Timing":"Qualquer",
         "Evidência":"Grau A","Fases":"Todas","Ref":"Kreider et al., 2017"},
        {"Suplemento":"Cafeína","Dose":f"{round(atleta.peso*4)}–{round(atleta.peso*6)}mg",
         "Timing":"45–60min pré","Evidência":"Grau A","Fases":"Todas","Ref":"Grgic et al., 2019"},
        {"Suplemento":"Beta-Alanina","Dose":"3.2–6.4g/dia","Timing":"Com refeições",
         "Evidência":"Grau A","Fases":"Todas","Ref":"Hobson et al., 2012"},
        {"Suplemento":"Whey Protein","Dose":"20–40g","Timing":"Pós-treino",
         "Evidência":"Grau A","Fases":"Todas","Ref":"Morton et al., 2018"},
        {"Suplemento":"Vitamina D3 + K2","Dose":"2000–4000 UI D3","Timing":"Com gordura",
         "Evidência":"Grau B","Fases":"Todas","Ref":"Holick et al., 2011"},
        {"Suplemento":"Ômega-3 (EPA+DHA)","Dose":"2–4g/dia","Timing":"Com refeições",
         "Evidência":"Grau B","Fases":"Todas","Ref":"Smith et al., 2011"},
    ]
    if atleta.fase_sugerida in ["Cutting","Pre-Contest (Cutting)"]:
        base.append({"Suplemento":"L-Carnitina Tartarato","Dose":"2g/dia",
            "Timing":"Pré-cardio","Evidência":"Grau B","Fases":"Cutting","Ref":"Wall et al., 2011"})
    if atleta.uso_peds:
        base.append({"Suplemento":"TUDCA (suporte hepático)","Dose":"250–500mg/dia",
            "Timing":"Com refeições","Evidência":"Grau B","Fases":"PEDs","Ref":"Larghi et al., 2006"})
    return pd.DataFrame(base)