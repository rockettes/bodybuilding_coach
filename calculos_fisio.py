"""
calculos_fisio.py
─────────────────────────────────────────────────────────────────────────────
Módulo central de cálculos fisiológicos para periodização IFBB Pro.
Todas as funções são baseadas em literatura científica peer-reviewed.
As referências são importadas de references.py e linkadas a cada função.

Arquitetura dos módulos:
  1. AtletaMetrics         — Dataclass com todas as métricas do atleta
  2. sugerir_fase_e_timeline — Periodização adaptativa (DUP + dados históricos)
  3. calcular_macros_semana  — Nutrição adaptativa com termogênese adaptativa
  4. calcular_zonas_karvonen — Zonas de FC para cardio
  5. prescrever_treino_do_dia — Autorregulação por VFC + ACWR
  6. gerar_treino_semanal    — Plano MEV/MAV/MRV com RIR e técnicas avançadas
  7. recomendar_suplementos  — Suplementação baseada em evidências Grau A/B
"""

import math
import random
from datetime import datetime, timedelta
from typing import Dict, Tuple, List, Optional
from dataclasses import dataclass, field
import pandas as pd
import numpy as np

from references import REFERENCIAS


# ─────────────────────────────────────────────────────────────────────────────
# 1. DATACLASS DO ATLETA
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class AtletaMetrics:
    """
    Contém todas as métricas estáticas e dinâmicas do atleta.
    Usado como parâmetro único em todas as funções de cálculo.
    """
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
    data_competicao: datetime


# ─────────────────────────────────────────────────────────────────────────────
# 2. PERIODIZAÇÃO ADAPTATIVA
# ─────────────────────────────────────────────────────────────────────────────

def _calcular_taxa_perda_peso(df_historico: pd.DataFrame) -> Optional[float]:
    """
    Calcula a taxa de perda de peso (%/semana) com base nas últimas 2 semanas do histórico.
    Retorna None se dados insuficientes (< 7 registros).
    """
    if df_historico.empty or "Peso" not in df_historico.columns:
        return None
    df_sorted = df_historico.dropna(subset=["Peso", "Data"]).sort_values("Data")
    if len(df_sorted) < 7:
        return None
    peso_atual = df_sorted.iloc[-1]["Peso"]
    peso_ha_14_dias = df_sorted.iloc[max(0, len(df_sorted) - 14)]["Peso"]
    if peso_ha_14_dias == 0:
        return None
    variacao_total = peso_ha_14_dias - peso_atual
    taxa_semanal_pct = (variacao_total / peso_ha_14_dias) * 100 / 2
    return round(taxa_semanal_pct, 3)


def _calcular_vfc_media_7dias(df_historico: pd.DataFrame) -> Optional[float]:
    """Calcula a média de VFC dos últimos 7 registros disponíveis."""
    if df_historico.empty or "VFC_Atual" not in df_historico.columns:
        return None
    df_sorted = df_historico.dropna(subset=["VFC_Atual"]).sort_values("Data")
    ultimos = df_sorted.tail(7)["VFC_Atual"].astype(float)
    if len(ultimos) < 3:
        return None
    return round(ultimos.mean(), 1)


def _detectar_plato_metabolico(df_historico: pd.DataFrame, fase: str) -> bool:
    """
    Detecta platô metabólico durante o cutting.
    Critério: perda < 0.5%/semana por 2 semanas consecutivas.
    Ref: Peos et al. (2019) — REFERENCIAS['peos_2019']
    """
    if fase not in ["Cutting", "Pre-Contest (Cutting)"]:
        return False
    taxa = _calcular_taxa_perda_peso(df_historico)
    if taxa is None:
        return False
    return taxa < 0.5


def sugerir_fase_e_timeline(
    data_atual: datetime,
    data_competicao: datetime,
    bf_atual: float,
    sexo: str,
    df_historico: pd.DataFrame
) -> Tuple[str, pd.DataFrame, Dict]:
    """
    Sugere a fase de periodização atual e projeta o timeline futuro.

    Lógica adaptativa (DUP):
    - Cruzamento de: dias para o show, BF atual, taxa de variação de peso,
      VFC média 7 dias vs baseline.
    - Detecção automática de Platô Metabólico durante o cutting.

    Refs:
        - Rhea et al. (2002): REFERENCIAS['rhea_2002']
        - Miranda et al. (2011): REFERENCIAS['miranda_2011']
        - Peos et al. (2019): REFERENCIAS['peos_2019']

    Returns:
        Tuple[str, pd.DataFrame, Dict]:
            - Fase sugerida (str)
            - DataFrame do timeline
            - Dict com flags diagnósticos (platô, instabilidade VFC etc.)
    """
    dias_totais = (data_competicao - data_atual).days
    fases_timeline = []
    flags = {
        "plato_metabolico": False,
        "taxa_perda_peso": None,
        "vfc_media_7d": None,
        "dados_insuficientes_peso": False,
        "dados_insuficientes_vfc": False,
    }

    # Processar histórico passado
    if not df_historico.empty and "Fase_Historica" in df_historico.columns:
        df_hist = df_historico.dropna(subset=["Fase_Historica", "Data"]).sort_values("Data")
        if not df_hist.empty:
            start_date = df_hist.iloc[0]["Data"]
            current_fase = df_hist.iloc[0]["Fase_Historica"]
            for _, row in df_hist.iterrows():
                if row["Fase_Historica"] != current_fase:
                    fases_timeline.append(dict(Fase=_fase_nome(current_fase), Inicio=start_date, Fim=row["Data"]))
                    start_date = row["Data"]
                    current_fase = row["Fase_Historica"]
            fases_timeline.append(dict(Fase=_fase_nome(current_fase), Inicio=start_date, Fim=data_atual.strftime("%Y-%m-%d")))

    # Calcular flags de diagnóstico
    taxa_perda = _calcular_taxa_perda_peso(df_historico)
    vfc_media = _calcular_vfc_media_7dias(df_historico)
    flags["taxa_perda_peso"] = taxa_perda
    flags["vfc_media_7d"] = vfc_media
    flags["dados_insuficientes_peso"] = taxa_perda is None
    flags["dados_insuficientes_vfc"] = vfc_media is None

    # Projeção futura
    dias_peak_week = 7
    dias_cutting = 112
    limite_bf_off = 15.0 if sexo == "Masculino" else 22.0

    if dias_totais <= 0:
        fase_atual = "Pós-Campeonato / Transição"
        fases_timeline.append(dict(Fase="Projeção: " + fase_atual, Inicio=data_atual, Fim=data_atual + timedelta(days=30)))
        return fase_atual, pd.DataFrame(fases_timeline), flags

    inicio_peak_week = data_competicao - timedelta(days=dias_peak_week)
    inicio_cutting = inicio_peak_week - timedelta(days=dias_cutting)

    if data_atual < inicio_cutting:
        fase_off = "Bulking" if bf_atual < limite_bf_off else "Recomposição Corporal"
        fases_timeline.append(dict(Fase="Projeção: " + fase_off, Inicio=data_atual, Fim=inicio_cutting))
        fases_timeline.append(dict(Fase="Projeção: Cutting", Inicio=inicio_cutting, Fim=inicio_peak_week))
        fases_timeline.append(dict(Fase="Projeção: Peak Week", Inicio=inicio_peak_week, Fim=data_competicao))
        fase_atual = fase_off
    elif data_atual >= inicio_cutting and data_atual < inicio_peak_week:
        fases_timeline.append(dict(Fase="Projeção: Cutting", Inicio=data_atual, Fim=inicio_peak_week))
        fases_timeline.append(dict(Fase="Projeção: Peak Week", Inicio=inicio_peak_week, Fim=data_competicao))
        fase_atual = "Cutting"
        flags["plato_metabolico"] = _detectar_plato_metabolico(df_historico, fase_atual)
    else:
        fases_timeline.append(dict(Fase="Projeção: Peak Week", Inicio=data_atual, Fim=data_competicao))
        fase_atual = "Peak Week"

    return fase_atual, pd.DataFrame(fases_timeline), flags


def _fase_nome(fase_str: str) -> str:
    return f"Histórico: {fase_str}"


# ─────────────────────────────────────────────────────────────────────────────
# 3. MÓDULO NUTRICIONAL ADAPTATIVO
# ─────────────────────────────────────────────────────────────────────────────

def calcular_tmb_katch_mcardle(peso: float, bf: float) -> float:
    """
    Fórmula de Katch-McArdle usando massa magra.
    Mais precisa que Harris-Benedict para atletas com BF medido.
    TMB = 370 + (21.6 × Massa Magra em kg)
    """
    massa_magra = peso * (1 - (bf / 100))
    return 370 + (21.6 * massa_magra)


def _calcular_semanas_em_deficit(df_historico: pd.DataFrame, fase: str) -> int:
    """
    Estima semanas contínuas em déficit com base no histórico de fase.
    Usado para termogênese adaptativa.
    Ref: Trexler et al. (2014) — REFERENCIAS['trexler_2014']
    """
    if df_historico.empty or "Fase_Historica" not in df_historico.columns:
        return 0
    df_sorted = df_historico.dropna(subset=["Fase_Historica"]).sort_values("Data", ascending=False)
    semanas = 0
    for _, row in df_sorted.iterrows():
        if row["Fase_Historica"] in ["Cutting", "Pre-Contest (Cutting)"]:
            semanas += 1
        else:
            break
    return max(0, (semanas // 7))


def calcular_macros_semana(
    atleta: AtletaMetrics,
    df_historico: pd.DataFrame = None,
    flags: Dict = None
) -> Tuple[pd.DataFrame, str, Dict]:
    """
    Gera ciclo semanal de macros com ajuste adaptativo de calorias.

    Lógica nutricional:
    - TMB via Katch-McArdle (usa LBM, não peso total)
    - Proteína calculada por kg de LBM (não peso total)
    - Termogênese adaptativa: -15kcal/semana de déficit após 4 semanas contínuas
    - Gordura mínima absoluta: 0.5g/kg para preservação hormonal
    - Cutting: Carb Cycling 5:2 (5 dias déficit + 2 dias refeed)
    - Peak Week: Protocolo depleção → supercompensação

    Refs:
        - Helms et al. (2014): REFERENCIAS['helms_2014']
        - Morton et al. (2018): REFERENCIAS['morton_2018']
        - Hall & Kahan (2018): REFERENCIAS['hall_2018']
        - Trexler et al. (2014): REFERENCIAS['trexler_2014']
        - Hamäläinen et al. (1984, 1985): REFERENCIAS['hamalainen_1984']
        - Campbell et al. (2020): REFERENCIAS['campbell_2020']
        - Chappell et al. (2018): REFERENCIAS['chappell_2018']
    """
    if df_historico is None:
        df_historico = pd.DataFrame()
    if flags is None:
        flags = {}

    tmb = calcular_tmb_katch_mcardle(atleta.peso, atleta.bf_atual)
    get = tmb * 1.55
    lbm = atleta.peso * (1 - (atleta.bf_atual / 100))

    dias_semana = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]
    plano_dieta = []
    alertas = {}

    # Ajuste adaptativo baseado na taxa de perda de peso (Hall & Kahan, 2018)
    ajuste_adaptativo = 0
    taxa_perda = flags.get("taxa_perda_peso")
    if taxa_perda is not None:
        if taxa_perda > 1.0:  # Perda muito rápida → aumentar calorias
            ajuste_adaptativo = +100
            alertas["ajuste_calórico"] = "⚠️ Taxa de perda > 1%/semana: +100kcal adicionadas para preservar massa magra. (Hall & Kahan, 2018)"
        elif taxa_perda < 0.5 and atleta.estagnado_dias >= 14:  # Platô → reduzir
            ajuste_adaptativo = -150
            alertas["ajuste_calórico"] = "⚠️ Platô metabólico detectado (< 0.5%/sem por 14d): -150kcal aplicadas. (Hall & Kahan, 2018)"

    # Termogênese adaptativa (Trexler et al., 2014)
    semanas_deficit = _calcular_semanas_em_deficit(df_historico, atleta.fase_sugerida)
    supressao_metabolica = 0
    if semanas_deficit > 4:
        supressao_metabolica = (semanas_deficit - 4) * 15
        alertas["supressao_metabolica"] = (
            f"⚠️ Termogênese Adaptativa: {semanas_deficit} semanas em déficit → "
            f"supressão estimada de -{supressao_metabolica}kcal/dia na TMB. "
            f"Considere diet break (Trexler et al., 2014)."
        )

    get_ajustado = get - supressao_metabolica + ajuste_adaptativo

    # ── BULKING ──────────────────────────────────────────────────────────────
    if atleta.fase_sugerida == "Bulking":
        surplus = 500 if atleta.uso_peds else 300
        calorias = get_ajustado + surplus
        # Proteína: 1.6–2.2g/kg LBM (Morton et al., 2018)
        prot_por_lbm = 2.2 if atleta.uso_peds else 1.8
        prot = lbm * prot_por_lbm
        # Gordura mínima: 0.5g/kg (Hamäläinen 1984, 1985)
        gord = max(atleta.peso * 1.0, atleta.peso * 0.5)
        carb = max(0, (calorias - (prot * 4) - (gord * 9)) / 4)
        for dia in dias_semana:
            plano_dieta.append({"Dia": dia, "Estratégia": "Superávit Base", "Calorias": round(calorias), "Carb(g)": round(carb), "Prot(g)": round(prot), "Gord(g)": round(gord)})
        motivo = (
            f"**Bulking Estável:** Superávit de {surplus}kcal ({'+500' if atleta.uso_peds else '+300'}kcal para PEDs). "
            f"Proteína: {prot_por_lbm}g/kg de LBM ({lbm:.1f}kg). "
            f"GET ajustado: {get_ajustado:.0f}kcal. "
            f"*(Iraki et al., 2019; Morton et al., 2018)*"
        )

    # ── CUTTING (Carb Cycling 5:2) ────────────────────────────────────────
    elif atleta.fase_sugerida in ["Cutting", "Pre-Contest (Cutting)"]:
        deficit_base = 500
        if flags.get("plato_metabolico"):
            deficit_base = 650
            alertas["plato_cutting"] = (
                "🔴 Protocolo de Quebra de Platô ativado: déficit aumentado para 650kcal. "
                "Refeed de 2 dias programado. *(Peos et al., 2019)*"
            )
        calorias_base = get_ajustado - deficit_base
        # Proteína: 2.4–3.1g/kg LBM no cutting (Helms et al., 2014)
        prot_por_lbm = 3.1 if not atleta.uso_peds else 2.5
        prot = lbm * prot_por_lbm
        # Gordura mínima absoluta: 0.5g/kg (Hamäläinen 1984)
        gord = max(atleta.peso * 0.7, atleta.peso * 0.5)
        carb_low = max(0, (calorias_base - (prot * 4) - (gord * 9)) / 4)
        # Refeed: retorno à manutenção — diferença vai 100% para carboidratos (Campbell et al., 2020)
        carb_refeed = carb_low + ((get_ajustado - calorias_base) / 4)
        for i, dia in enumerate(dias_semana):
            if i < 5:
                plano_dieta.append({"Dia": dia, "Estratégia": "Low Carb (Déficit)", "Calorias": round(calorias_base), "Carb(g)": round(carb_low), "Prot(g)": round(prot), "Gord(g)": round(gord)})
            else:
                plano_dieta.append({"Dia": dia, "Estratégia": "Refeed (Manutenção)", "Calorias": round(get_ajustado), "Carb(g)": round(carb_refeed), "Prot(g)": round(prot), "Gord(g)": round(gord)})
        motivo = (
            f"**Carb Cycling 5:2** (5 dias déficit de {deficit_base}kcal + 2 dias Refeed na manutenção). "
            f"Proteína: {prot_por_lbm}g/kg LBM = {prot:.0f}g. "
            f"Refeed estimula leptina e preserva TMB. "
            f"*(Helms et al., 2014; Campbell et al., 2020)*"
        )

    # ── PEAK WEEK ─────────────────────────────────────────────────────────
    elif atleta.fase_sugerida == "Peak Week":
        # Depleção: prot alta, carb quase zero, gord moderada
        prot_dep = atleta.peso * 3.0
        gord_dep = max(atleta.peso * 0.8, atleta.peso * 0.5)
        carb_dep = 50.0
        cal_dep = (prot_dep * 4) + (gord_dep * 9) + (carb_dep * 4)
        # Carb-Up: 8g/kg com gord mínima
        prot_up = atleta.peso * 2.0
        gord_up = max(atleta.peso * 0.4, atleta.peso * 0.5)
        carb_up = atleta.peso * 8.0
        cal_up = (prot_up * 4) + (gord_up * 9) + (carb_up * 4)
        # Dia do show / spillover check
        carb_show = max(0, (get_ajustado - (prot_dep * 4) - (gord_up * 9)) / 4)
        estrategias = ["Depleção Extrema", "Depleção Extrema", "Depleção Extrema", "Carb-Up (Loading)", "Carb-Up (Loading)", "Spillover Check", "Dia do Show"]
        for i, dia in enumerate(dias_semana):
            if i < 3:
                plano_dieta.append({"Dia": dia, "Estratégia": estrategias[i], "Calorias": round(cal_dep), "Carb(g)": round(carb_dep), "Prot(g)": round(prot_dep), "Gord(g)": round(gord_dep)})
            elif i < 5:
                plano_dieta.append({"Dia": dia, "Estratégia": estrategias[i], "Calorias": round(cal_up), "Carb(g)": round(carb_up), "Prot(g)": round(prot_up), "Gord(g)": round(gord_up)})
            else:
                plano_dieta.append({"Dia": dia, "Estratégia": estrategias[i], "Calorias": round(get_ajustado), "Carb(g)": round(carb_show), "Prot(g)": round(prot_dep), "Gord(g)": round(gord_up)})
        motivo = (
            "**Peak Week Protocol:** Dias 1–3: depleção severa de glicogênio (50g carb/dia). "
            "Dias 4–5: Carb-Up massivo (8g/kg, gordura mínima) para supercompensação. "
            "Dias 6–7: manutenção e ajuste de water/sodium. "
            "*(Chappell et al., 2018)*"
        )

    # ── RECOMPOSIÇÃO ──────────────────────────────────────────────────────
    else:
        calorias = get_ajustado - 200
        prot = lbm * 2.5
        gord = max(atleta.peso * 0.9, atleta.peso * 0.5)
        carb = max(0, (calorias - (prot * 4) - (gord * 9)) / 4)
        for dia in dias_semana:
            plano_dieta.append({"Dia": dia, "Estratégia": "Leve Déficit", "Calorias": round(calorias), "Carb(g)": round(carb), "Prot(g)": round(prot), "Gord(g)": round(gord)})
        motivo = (
            "**Recomposição Corporal:** Leve déficit (~200kcal) para perda de gordura lenta "
            "sem interromper síntese proteica. Proteína: 2.5g/kg LBM. "
            "*(Barakat et al., 2020)*"
        )

    alertas["get_base"] = f"TMB (Katch-McArdle): {tmb:.0f}kcal | GET (×1.55): {get:.0f}kcal | GET Ajustado: {get_ajustado:.0f}kcal | LBM: {lbm:.1f}kg"
    if supressao_metabolica > 0:
        alertas["get_base"] += f" | Supressão adapt.: -{supressao_metabolica}kcal"

    return pd.DataFrame(plano_dieta), motivo, alertas


# ─────────────────────────────────────────────────────────────────────────────
# 4. ZONAS DE FREQUÊNCIA CARDÍACA (KARVONEN)
# ─────────────────────────────────────────────────────────────────────────────

def calcular_zonas_karvonen(idade: int, fc_repouso: int) -> Dict[str, Tuple[int, int]]:
    """
    Calcula zonas de FC pelo método Karvonen (Reserva de FC).
    FC Máxima estimada pela equação de Tanaka: 208 - (0.7 × idade).
    """
    fc_max = 208 - (0.7 * idade)
    fcr = fc_max - fc_repouso
    return {
        "Zona 1 (Recuperação Ativa)": (int((fcr * 0.50) + fc_repouso), int((fcr * 0.60) + fc_repouso)),
        "Zona 2 (LISS / Fat-Burning)": (int((fcr * 0.60) + fc_repouso), int((fcr * 0.70) + fc_repouso)),
        "Zona 3 (Aeróbio Moderado)": (int((fcr * 0.70) + fc_repouso), int((fcr * 0.80) + fc_repouso)),
        "Zona 4 (Limiar Anaeróbio)": (int((fcr * 0.80) + fc_repouso), int((fcr * 0.90) + fc_repouso)),
        "Zona 5 (HIIT / Máximo)": (int((fcr * 0.90) + fc_repouso), int(fc_max)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. RECUPERAÇÃO: VFC + ACWR
# ─────────────────────────────────────────────────────────────────────────────

def calcular_acwr(df_historico: pd.DataFrame) -> Tuple[Optional[float], str]:
    """
    Calcula o ACWR (Acute:Chronic Workload Ratio).
    - Carga Aguda = média de carga dos últimos 7 dias
    - Carga Crônica = média de carga dos últimos 28 dias
    - Zona segura: 0.8–1.3 (Gabbett, 2016)

    Refs:
        - Gabbett (2016): REFERENCIAS['gabbett_2016']
        - Hulin et al. (2016): REFERENCIAS['hulin_2016']

    Returns:
        Tuple[Optional[float], str]: (valor ACWR ou None, mensagem de status)
    """
    if df_historico.empty or "Carga_Treino" not in df_historico.columns:
        return None, "⚠️ Dados insuficientes para calcular ACWR (mínimo 7 registros)."
    df_sorted = df_historico.dropna(subset=["Carga_Treino"]).sort_values("Data")
    if len(df_sorted) < 7:
        return None, f"⚠️ Apenas {len(df_sorted)} registros disponíveis. Mínimo 7 para ACWR."
    carga_aguda = df_sorted.tail(7)["Carga_Treino"].astype(float).mean()
    carga_cronica = df_sorted.tail(28)["Carga_Treino"].astype(float).mean()
    if carga_cronica == 0:
        return None, "⚠️ Carga crônica = 0. Registre mais treinos para calcular ACWR."
    acwr = round(carga_aguda / carga_cronica, 2)
    if acwr < 0.8:
        status = f"🔵 ACWR = {acwr} | Abaixo do ideal — risco de destreinamento (< 0.8)"
    elif acwr <= 1.3:
        status = f"🟢 ACWR = {acwr} | Zona segura (0.8–1.3) — carga bem gerenciada"
    elif acwr <= 1.5:
        status = f"🟡 ACWR = {acwr} | Zona amarela (1.3–1.5) — monitorar fadiga acumulada"
    else:
        status = f"🔴 ACWR = {acwr} | ZONA DE RISCO (> 1.5) — risco elevado de lesão por sobrecarga"
    return acwr, status


def calcular_cv_vfc(df_historico: pd.DataFrame) -> Tuple[Optional[float], str]:
    """
    Calcula o Coeficiente de Variação (CV%) da VFC dos últimos 7 dias.
    CV > 10% indica instabilidade autonômica.

    Ref: Flatt & Esco (2016) — REFERENCIAS['flatt_2016']
    """
    if df_historico.empty or "VFC_Atual" not in df_historico.columns:
        return None, "⚠️ Dados insuficientes para calcular CV da VFC."
    df_sorted = df_historico.dropna(subset=["VFC_Atual"]).sort_values("Data")
    ultimos = df_sorted.tail(7)["VFC_Atual"].astype(float)
    if len(ultimos) < 5:
        return None, f"⚠️ Apenas {len(ultimos)} registros de VFC. Mínimo 5 para CV confiável."
    cv = (ultimos.std() / ultimos.mean()) * 100
    cv = round(cv, 1)
    if cv > 10:
        status = f"🔴 CV VFC = {cv}% | Instabilidade autonômica detectada (> 10%). Reduza volume de treino. *(Flatt & Esco, 2016)*"
    elif cv > 7:
        status = f"🟡 CV VFC = {cv}% | Variabilidade moderada. Monitore recuperação. *(Flatt & Esco, 2016)*"
    else:
        status = f"🟢 CV VFC = {cv}% | SNC estável. *(Flatt & Esco, 2016)*"
    return cv, status


def prescrever_treino_do_dia(
    atleta: AtletaMetrics,
    df_historico: pd.DataFrame = None
) -> Tuple[str, str, str, str, Optional[float], str, Optional[float], str]:
    """
    Prescreve a ação do dia com base em VFC, Sleep Score, Recovery Time, ACWR e CV VFC.

    Modelo de decisão (multi-variável):
    1. Queda de VFC vs baseline (Jamieson, 2009)
    2. Sleep Score
    3. Recovery Time Garmin
    4. ACWR (Gabbett, 2016)
    5. CV da VFC (Flatt & Esco, 2016)

    Refs:
        - Flatt & Esco (2016): REFERENCIAS['flatt_2016']
        - Jamieson (2009): REFERENCIAS['jamieson_2009']
        - Kiviniemi et al. (2007): REFERENCIAS['kiviniemi_2007']
        - Gabbett (2016): REFERENCIAS['gabbett_2016']
    """
    if df_historico is None:
        df_historico = pd.DataFrame()

    queda_vfc_pct = ((atleta.vfc_base - atleta.vfc_atual) / atleta.vfc_base) * 100
    texto_vfc = f"Queda de {queda_vfc_pct:.1f}%" if queda_vfc_pct > 0 else f"Aumento de {abs(queda_vfc_pct):.1f}%"

    acwr, acwr_status = calcular_acwr(df_historico)
    cv_vfc, cv_status = calcular_cv_vfc(df_historico)

    painel_metricas = (
        f"⚙️ **Análise Algoritmo:** VFC: **{texto_vfc}** | "
        f"Sleep: **{atleta.sleep_score}/100** | "
        f"Recovery: **{atleta.recovery_time}h** | "
        f"FC Repouso: **{atleta.fc_repouso}bpm**"
    )

    # Pontuação de fadiga (0 = ótimo, maior = mais fatigado)
    pontos_fadiga = 0
    if queda_vfc_pct >= 15: pontos_fadiga += 3
    elif queda_vfc_pct >= 7: pontos_fadiga += 2
    elif queda_vfc_pct >= 3: pontos_fadiga += 1

    if atleta.sleep_score < 50: pontos_fadiga += 2
    elif atleta.sleep_score < 70: pontos_fadiga += 1

    if atleta.recovery_time >= 48: pontos_fadiga += 2
    elif atleta.recovery_time >= 36: pontos_fadiga += 1

    if acwr is not None and acwr > 1.5: pontos_fadiga += 2
    elif acwr is not None and acwr > 1.3: pontos_fadiga += 1

    if cv_vfc is not None and cv_vfc > 10: pontos_fadiga += 1

    # Decisão final baseada na pontuação de fadiga
    if pontos_fadiga >= 5:
        status_dia = "🔴 Fadiga Severa (SNC Suprimido)"
        acao_dia = "DESCANSO TOTAL — Nenhum treino. Foco em recuperação (sono, alimentação, hidratação)."
        motivo_dia = (
            "Supressão parassimpática severa detectada (múltiplos marcadores negativos). "
            "Treinar nesta condição aumenta cortisol crônico, catabolismo e risco de overtraining. "
            "*(Jamieson, 2009; Flatt & Esco, 2016)*"
        )
    elif pontos_fadiga >= 3:
        status_dia = "🟡 Recuperação Incompleta"
        acao_dia = "CARDIO ZONA 2 APENAS — 30 a 45 min, FC 60-70% FCR. Sem musculação."
        motivo_dia = (
            "SNC em recuperação parcial. Cardio Zona 2 estimula atividade parassimpática "
            "e fluxo sanguíneo sem gerar novo estresse de SNC. "
            "*(Jamieson, 2009; Kiviniemi et al., 2007)*"
        )
    else:
        status_dia = "🟢 Totalmente Recuperado"
        acao_dia = "TREINO DE MUSCULAÇÃO NORMAL — Consulte o plano semanal abaixo."
        motivo_dia = (
            "Todos os marcadores de recuperação dentro do esperado. "
            "Prontidão total do SNC para treinamento de alta intensidade. "
            "*(Kiviniemi et al., 2007)*"
        )

    return status_dia, acao_dia, motivo_dia, painel_metricas, acwr, acwr_status, cv_vfc, cv_status


# ─────────────────────────────────────────────────────────────────────────────
# 6. MÓDULO DE TREINO: MEV / MAV / MRV + RIR + TÉCNICAS AVANÇADAS
# ─────────────────────────────────────────────────────────────────────────────

# Volume por grupo muscular (séries/semana) baseado em Israetel et al. (2019)
VOLUME_CONFIG = {
    "Bulking": {
        "series_por_musculo": 18,  # MAV
        "series_por_musculo_min": 14,
        "series_por_musculo_max": 20,
        "reps": "8-12",
        "descanso": 90,
        "rir": "1-2",
        "tecnica_intensidade": "Rest-Pause ou Drop-Set nas últimas séries",
        "progressao_pct": 2.5,
    },
    "Cutting": {
        "series_por_musculo": 10,  # Entre MEV e MAV
        "series_por_musculo_min": 8,
        "series_por_musculo_max": 12,
        "reps": "6-8",
        "descanso": 120,
        "rir": "0-1",
        "tecnica_intensidade": "Superséries Antagonistas (densidade máxima)",
        "progressao_pct": 0.0,
    },
    "Peak Week": {
        "series_por_musculo": 7,  # MEV apenas
        "series_por_musculo_min": 6,
        "series_por_musculo_max": 8,
        "reps": "12-15",
        "descanso": 60,
        "rir": "3-4",
        "tecnica_intensidade": "Sem técnicas avançadas — controle máximo",
        "progressao_pct": 0.0,
    },
    "Recomposição Corporal": {
        "series_por_musculo": 12,
        "series_por_musculo_min": 10,
        "series_por_musculo_max": 15,
        "reps": "10-12",
        "descanso": 75,
        "rir": "1-2",
        "tecnica_intensidade": "Superséries ou Rest-Pause (moderado)",
        "progressao_pct": 2.0,
    },
}

DIVISAO_TREINO = {
    "Peito + Ombro + Tríceps": {
        "grupos": ["Peitoral", "Peitoral Superior", "Peitoral Inferior", "Deltóide Anterior", "Deltóide Lateral", "Deltóide Posterior", "Trapézio Superior", "Tríceps", "Tríceps (Cabeça Longa)"],
        "exercicios_por_grupo": 2,
    },
    "Costas + Bíceps + Posterior": {
        "grupos": ["Latíssimo do Dorso", "Dorsal (Espessura)", "Romboides", "Bíceps", "Bíceps (Cabeça Longa)", "Braquiorradial", "Isquiotibiais", "Glúteo Máximo", "Glúteo Médio"],
        "exercicios_por_grupo": 2,
    },
    "Pernas + Panturrilha + Abs": {
        "grupos": ["Quadríceps", "Isquiotibiais", "Glúteo Máximo", "Glúteo Médio", "Gastrocnêmio", "Sóleo", "Reto Abdominal", "Oblíquos", "Core (Transverso Abdominal)"],
        "exercicios_por_grupo": 2,
    },
}


def gerar_treino_semanal(
    atleta: AtletaMetrics,
    exercicios_db: List[Dict]
) -> Tuple[pd.DataFrame, str]:
    """
    Gera plano semanal de treino com:
    - Volume baseado em MEV/MAV/MRV (Israetel et al., 2019)
    - RIR alvo por fase (Zourdos et al., 2016)
    - Técnicas de intensidade por fase (Schoenfeld 2011; Weakley et al., 2017)
    - Progressão de carga semanal (Ralston et al., 2017)
    - Seleção aleatória de exercícios (Fonseca et al., 2014)

    Refs:
        - Israetel et al. (2019): REFERENCIAS['israetel_2019']
        - Schoenfeld (2010/2011): REFERENCIAS['schoenfeld_2010'], REFERENCIAS['schoenfeld_2011']
        - Zourdos et al. (2016): REFERENCIAS['zourdos_2016']
        - Ralston et al. (2017): REFERENCIAS['ralston_2017']
        - Fonseca et al. (2014): REFERENCIAS['fonseca_2014']
        - Weakley et al. (2017): REFERENCIAS['weakley_2017']
    """
    fase = atleta.fase_sugerida
    config = VOLUME_CONFIG.get(fase, VOLUME_CONFIG["Recomposição Corporal"])

    # Calcular séries por exercício: distribuir volume alvo por número de exercícios
    series_base = 4 if fase == "Bulking" else 3

    plano_semanal = []
    for nome_treino, info in DIVISAO_TREINO.items():
        grupos = info["grupos"]
        ex_disponiveis = [ex for ex in exercicios_db if ex["musculo_principal_ativado"] in grupos]

        # Seleção aleatória para variação estímulo-específica (Fonseca et al., 2014)
        random.shuffle(ex_disponiveis)
        # Limitar ao volume alvo: ~6 exercícios para MAV, 4 para MEV
        max_exercicios = 6 if fase == "Bulking" else (4 if fase == "Peak Week" else 5)
        selecionados = ex_disponiveis[:max_exercicios]

        for i, ex in enumerate(selecionados):
            # Última série recebe técnica de intensidade no Bulking
            tecnica = ""
            if fase == "Bulking" and i == len(selecionados) - 1:
                tecnica = "Drop-Set" if i % 2 == 0 else "Rest-Pause"
            elif fase == "Cutting" and i % 2 == 0 and i < len(selecionados) - 1:
                tecnica = "Supersérie c/ próximo"

            plano_semanal.append({
                "Treino": nome_treino,
                "Exercício": ex["nome"],
                "Músculo Principal": ex["musculo_principal_ativado"],
                "Séries": series_base,
                "Reps": config["reps"],
                "RIR Alvo": config["rir"],
                "Descanso (s)": config["descanso"],
                "Técnica Intensidade": tecnica if tecnica else "—",
                "Progressão Sugerida": f"+{config['progressao_pct']}%/semana" if config["progressao_pct"] > 0 else "Manter carga",
            })

    motivo = (
        f"**{fase}** | Volume: {config['series_por_musculo_min']}–{config['series_por_musculo_max']} séries/músculo/sem (MEV→MRV) | "
        f"RIR: {config['rir']} | Técnica: {config['tecnica_intensidade']} | "
        f"Progressão: {config['progressao_pct']}%/semana. "
        f"*(Israetel et al., 2019; Zourdos et al., 2016; Ralston et al., 2017)*"
    )
    return pd.DataFrame(plano_semanal), motivo


# ─────────────────────────────────────────────────────────────────────────────
# 7. SUPLEMENTAÇÃO BASEADA EM EVIDÊNCIAS (GRAU A/B)
# ─────────────────────────────────────────────────────────────────────────────

def recomendar_suplementos(atleta: AtletaMetrics) -> pd.DataFrame:
    """
    Retorna recomendações de suplementação baseadas em evidências Grau A/B,
    filtradas e dosadas pela fase atual do atleta.

    Refs:
        - Kreider et al. (2017): REFERENCIAS['kreider_2017'] — Creatina
        - Grgic et al. (2019): REFERENCIAS['grgic_2019'] — Cafeína
        - Hobson et al. (2012): REFERENCIAS['hobson_2012'] — Beta-Alanina
        - Wilson et al. (2014): REFERENCIAS['wilson_2014'] — HMB
        - Chappell et al. (2018): REFERENCIAS['chappell_2018'] — Eletrólitos Peak Week
        - Hamäläinen et al. (1984, 1985) — Ômega-3 / Vitamina D suporte hormonal
    """
    fase = atleta.fase_sugerida
    peso = atleta.peso
    suplementos = []

    # Creatina — universal (Kreider et al., 2017)
    suplementos.append({
        "Suplemento": "Creatina Monohidratada",
        "Dose": "3–5g/dia",
        "Timing": "Qualquer horário (com refeição)",
        "Fase": "Todas",
        "Evidência": "Grau A",
        "Ativo na Fase": "✅",
        "Referência": "Kreider et al. (2017, JISSN)",
    })

    # Cafeína — bulking e cutting (Grgic et al., 2019)
    dose_cafeina = f"{round(peso * 3)}–{round(peso * 6)}mg"
    suplementos.append({
        "Suplemento": "Cafeína",
        "Dose": dose_cafeina,
        "Timing": "60 min pré-treino",
        "Fase": "Bulking / Cutting",
        "Evidência": "Grau A",
        "Ativo na Fase": "✅" if fase in ["Bulking", "Cutting", "Recomposição Corporal"] else "⏸️ Cautela em Peak Week",
        "Referência": "Grgic et al. (2019, BJSM)",
    })

    # Beta-Alanina — alto volume (Hobson et al., 2012)
    suplementos.append({
        "Suplemento": "Beta-Alanina",
        "Dose": "3.2–6.4g/dia (dividida em doses)",
        "Timing": "Junto às refeições (reduz parestesia)",
        "Fase": "Bulking / Cutting (volume ≥10 séries/treino)",
        "Evidência": "Grau A",
        "Ativo na Fase": "✅" if fase in ["Bulking", "Cutting", "Recomposição Corporal"] else "❌ Desnecessário em Peak Week",
        "Referência": "Hobson et al. (2012, Amino Acids)",
    })

    # HMB — apenas cutting severo / peak week (Wilson et al., 2014)
    suplementos.append({
        "Suplemento": "HMB (Forma Livre — HMB-FA)",
        "Dose": "3g/dia (1g × 3 doses)",
        "Timing": "Junto às refeições",
        "Fase": "Cutting severo / Peak Week",
        "Evidência": "Grau B",
        "Ativo na Fase": "✅" if fase in ["Cutting", "Peak Week", "Pre-Contest (Cutting)"] else "❌ Não indicado nesta fase",
        "Referência": "Wilson et al. (2014, Eur J Appl Physiol)",
    })

    # Vitamina D — universal
    suplementos.append({
        "Suplemento": "Vitamina D3 + K2",
        "Dose": "2000–5000 UI/dia",
        "Timing": "Com refeição gordurosa",
        "Fase": "Todas",
        "Evidência": "Grau B",
        "Ativo na Fase": "✅",
        "Referência": "Hamäläinen et al. (1984); Consenso ISSN",
    })

    # Ômega-3 — universal
    suplementos.append({
        "Suplemento": "Ômega-3 (EPA+DHA)",
        "Dose": "2–4g/dia EPA+DHA",
        "Timing": "Com refeição",
        "Fase": "Todas",
        "Evidência": "Grau B",
        "Ativo na Fase": "✅",
        "Referência": "Hamäläinen et al. (1985); revisão ISSN",
    })

    # Eletrólitos — cutting e peak week (Chappell et al., 2018)
    if fase in ["Cutting", "Peak Week", "Pre-Contest (Cutting)"]:
        suplementos.append({
            "Suplemento": "Eletrólitos (Na + K + Mg)",
            "Dose": "Sódio: 2–4g/dia | Potássio: 3–4g/dia | Magnésio: 400mg/dia",
            "Timing": "Distribuído nas refeições",
            "Fase": "Cutting / Peak Week",
            "Evidência": "Grau B",
            "Ativo na Fase": "✅",
            "Referência": "Chappell et al. (2018, JISSN)",
        })

    return pd.DataFrame(suplementos)