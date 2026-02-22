# references.py
# Dicionário global de referências científicas em formato APA
# Indexadas por chave e categorizadas por módulo

REFERENCIAS = {
    # ─── PERIODIZAÇÃO ───────────────────────────────────────────────────────────
    "rhea_2002": {
        "modulo": "Periodização",
        "badge_color": "#6C63FF",
        "apa": (
            "Rhea, M. R., Ball, S. D., Phillips, W. T., & Burkett, L. N. (2002). "
            "A comparison of linear and daily undulating periodized programs with equated "
            "volume and intensity for strength. Journal of Strength and Conditioning Research, "
            "16(2), 250–255."
        ),
        "resumo": "Base do modelo DUP (Daily Undulating Periodization): variação diária de estímulo (força/hipertrofia/resistência) é superior à periodização linear para ganhos simultâneos de força e massa.",
    },
    "miranda_2011": {
        "modulo": "Periodização",
        "badge_color": "#6C63FF",
        "apa": (
            "Miranda, F., Simão, R., Rhea, M., Bunker, D., Prestes, J., Leite, R. D., ... & Novaes, J. (2011). "
            "Effects of linear vs. daily undulatory periodization on maximal and submaximal strength gains. "
            "Journal of Strength and Conditioning Research, 25(7), 1824–1830."
        ),
        "resumo": "Confirma superioridade da periodização ondulatória diária (DUP) sobre linear em contextos de hipertrofia e força máxima.",
    },
    "peos_2019": {
        "modulo": "Periodização",
        "badge_color": "#6C63FF",
        "apa": (
            "Peos, J. J., Norton, L. E., Helms, E. R., Appleby, S., & Ong, A. K. (2019). "
            "Intermittent dieting: theoretical considerations for the athlete. "
            "Current Sports Medicine Reports, 18(7), 254–260."
        ),
        "resumo": "Diet breaks de 1–2 semanas em manutenção calórica durante cortes prolongados atenuam a termogênese adaptativa e preservam a massa magra melhor que restrição contínua.",
    },

    # ─── NUTRIÇÃO ───────────────────────────────────────────────────────────────
    "helms_2014": {
        "modulo": "Nutrição",
        "badge_color": "#FF6B6B",
        "apa": (
            "Helms, E. R., Aragon, A. A., & Fitschen, P. J. (2014). "
            "Evidence-based recommendations for natural bodybuilding contest preparation: "
            "nutrition and supplementation. Journal of the International Society of Sports "
            "Nutrition, 11(1), 20."
        ),
        "resumo": "Proteína de 2.3–3.1g/kg de massa magra no cutting preserva massa muscular; déficit calórico de 500kcal/dia é seguro para atletas naturais com BF moderado.",
    },
    "morton_2018": {
        "modulo": "Nutrição",
        "badge_color": "#FF6B6B",
        "apa": (
            "Morton, R. W., Murphy, K. T., McKellar, S. R., Schoenfeld, B. J., Henselmans, M., "
            "Helms, E., ... & Phillips, S. M. (2018). "
            "A systematic review, meta-analysis and meta-regression of the effect of protein "
            "supplementation on resistance training-induced gains in muscle mass and strength "
            "in healthy adults. British Journal of Sports Medicine, 52(6), 376–384."
        ),
        "resumo": "Meta-análise: 1.62g/kg de proteína/dia maximiza ganhos de massa muscular no bulking; acima de 2.2g/kg não há benefício adicional para a maioria dos indivíduos.",
    },
    "hall_2018": {
        "modulo": "Nutrição",
        "badge_color": "#FF6B6B",
        "apa": (
            "Hall, K. D., & Kahan, S. (2018). "
            "Maintenance of lost weight and long-term management of obesity. "
            "Medical Clinics of North America, 102(1), 183–197."
        ),
        "resumo": "Ajuste adaptativo de calorias: perda acima de 1%/semana indica déficit excessivo; abaixo de 0.5%/semana por 2 semanas indica necessidade de redução calórica adicional ou refeed.",
    },
    "trexler_2014": {
        "modulo": "Nutrição",
        "badge_color": "#FF6B6B",
        "apa": (
            "Trexler, E. T., Smith-Ryan, A. E., & Norton, L. E. (2014). "
            "Metabolic adaptation to weight loss: implications for the athlete. "
            "Journal of the International Society of Sports Nutrition, 11(1), 7."
        ),
        "resumo": "Termogênese adaptativa: a TMB pode cair 15–20% além do esperado pela perda de massa. Após 4 semanas de déficit contínuo, reduções progressivas de ~15kcal/semana devem ser antecipadas.",
    },
    "hamalainen_1984": {
        "modulo": "Nutrição",
        "badge_color": "#FF6B6B",
        "apa": (
            "Hämäläinen, E. K., Adlercreutz, H., Puska, P., & Pietinen, P. (1984). "
            "Decrease of serum total and free testosterone during a low-fat high-fibre diet. "
            "Journal of Steroid Biochemistry, 20(1), 459–464."
        ),
        "resumo": "Dietas com gordura abaixo de 15–20% das calorias totais suprimem testosterona sérica total e livre em homens ativos.",
    },
    "hamalainen_1985": {
        "modulo": "Nutrição",
        "badge_color": "#FF6B6B",
        "apa": (
            "Hämäläinen, E., Adlercreutz, H., Puska, P., & Pietinen, P. (1985). "
            "Diet and serum sex hormones in healthy men. "
            "Journal of Steroid Biochemistry, 22(4), 459–464."
        ),
        "resumo": "Confirma relação positiva entre ingestão de gordura saturada/monoinsaturada e níveis de testosterona; gordura mínima de 0.5g/kg/dia para preservação hormonal.",
    },
    "iraki_2019": {
        "modulo": "Nutrição",
        "badge_color": "#FF6B6B",
        "apa": (
            "Iraki, J., Fitschen, P., Espinar, S., & Helms, E. (2019). "
            "Nutrition recommendations for bodybuilders in the off-season: a narrative review. "
            "Sports, 7(7), 154."
        ),
        "resumo": "Off-season: superávit de 300–500kcal/dia. PEDs podem suportar superávit mais agressivo (até 700kcal) sem acúmulo excessivo de gordura em comparação com naturais.",
    },
    "chappell_2018": {
        "modulo": "Nutrição",
        "badge_color": "#FF6B6B",
        "apa": (
            "Chappell, A. J., Simper, T., & Barker, M. E. (2018). "
            "Nutritional strategies of high level natural bodybuilders during competition preparation. "
            "Journal of the International Society of Sports Nutrition, 15(1), 4."
        ),
        "resumo": "Peak Week: depleção de glicogênio (dias 1–3) seguida de carb-up (8g/kg, dias 4–5) com gordura mínima (<0.5g/kg) para supercompensação. Manipulação de sódio e água na semana final.",
    },
    "campbell_2020": {
        "modulo": "Nutrição",
        "badge_color": "#FF6B6B",
        "apa": (
            "Campbell, B. I., Aguilar, D., Colenso-Semple, L. M., Hartke, K., Fleming, A. R., "
            "Fox, C. D., ... & Ford, S. (2020). "
            "Intermittent energy restriction attenuates the loss of fat free mass in resistance "
            "trained individuals. A randomized controlled trial. "
            "Journal of Functional Morphology and Kinesiology, 5(1), 19."
        ),
        "resumo": "Restrição calórica intermitente (5 dias déficit + 2 dias manutenção) preserva massa magra significativamente melhor que restrição calórica contínua de mesma magnitude.",
    },
    "barakat_2020": {
        "modulo": "Nutrição",
        "badge_color": "#FF6B6B",
        "apa": (
            "Barakat, C., Pearson, J., Escalante, G., Campbell, B., & De Souza, E. O. (2020). "
            "Body recomposition: can trained individuals build muscle and lose fat at the same time? "
            "Strength & Conditioning Journal, 42(5), 7–21."
        ),
        "resumo": "Recomposição corporal é viável em indivíduos treinados com déficit moderado (~200–300kcal) e proteína alta (≥2.4g/kg LBM), especialmente em iniciantes ou retorno ao treino.",
    },

    # ─── TREINO ─────────────────────────────────────────────────────────────────
    "israetel_2019": {
        "modulo": "Treino",
        "badge_color": "#4ECDC4",
        "apa": (
            "Israetel, M., Hoffman, J., & Smith, C. (2019). "
            "Scientific principles of hypertrophy training. "
            "Renaissance Periodization (RP Strength)."
        ),
        "resumo": "Framework MEV-MAV-MRV: volume mínimo efetivo (~8–10 séries/músculo/semana), volume máximo adaptativo (~15–20 séries) e volume máximo recuperável (~20–25 séries). Volume deve progredir ao longo do mesociclo.",
    },
    "schoenfeld_2010": {
        "modulo": "Treino",
        "badge_color": "#4ECDC4",
        "apa": (
            "Schoenfeld, B. J. (2010). "
            "The mechanisms of muscle hypertrophy and their application to resistance training. "
            "Journal of Strength and Conditioning Research, 24(10), 2857–2872."
        ),
        "resumo": "Três mecanismos de hipertrofia: tensão mecânica, dano muscular e estresse metabólico. Técnicas como Drop-Set e Rest-Pause maximizam os três mecanismos simultaneamente.",
    },
    "schoenfeld_2011": {
        "modulo": "Treino",
        "badge_color": "#4ECDC4",
        "apa": (
            "Schoenfeld, B. J. (2011). "
            "The use of specialized training techniques to maximize muscle hypertrophy. "
            "Strength & Conditioning Journal, 33(4), 60–65."
        ),
        "resumo": "Técnicas avançadas (Drop-Set, Rest-Pause, Superséries) aumentam densidade de treino e EPOC. Recomendadas nas últimas séries de exercícios compostos para maximizar estímulo.",
    },
    "weakley_2017": {
        "modulo": "Treino",
        "badge_color": "#4ECDC4",
        "apa": (
            "Weakley, J. J. S., Till, K., Read, D. B., Roe, G. A. B., Darrall-Jones, J., Phibbs, P. J., "
            "& Jones, B. (2017). "
            "The effects of superset configuration on kinetic, kinematic, and perceived exertion "
            "in the barbell bench press. European Journal of Sport Science, 17(9), 1151–1157."
        ),
        "resumo": "Superséries antagonistas reduzem tempo de treino em ~30% mantendo volume e intensidade. EPOC elevado promove gasto calórico aumentado pós-treino — ideal para cutting.",
    },
    "zourdos_2016": {
        "modulo": "Treino",
        "badge_color": "#4ECDC4",
        "apa": (
            "Zourdos, M. C., Klemp, A., Dolan, C., Quiles, J. M., Schau, K. A., Jo, E., ... "
            "& Whitehurst, M. (2016). "
            "Novel resistance training-specific rating of perceived exertion scale measuring "
            "repetitions in reserve. Journal of Strength and Conditioning Research, 30(1), 267–275."
        ),
        "resumo": "Escala RIR (Repetições em Reserva): RIR 0-1 = falha muscular próxima (alto estímulo, alto dano); RIR 2-3 = zona hipertrófica segura; RIR 3-4 = controle técnico máximo (ideal para Peak Week).",
    },
    "ralston_2017": {
        "modulo": "Treino",
        "badge_color": "#4ECDC4",
        "apa": (
            "Ralston, G. W., Kilgore, L., Wyatt, F. B., & Baker, J. S. (2017). "
            "The effect of weekly set volume on strength gain: a meta-analysis. "
            "Sports Medicine, 47(12), 2585–2601."
        ),
        "resumo": "Sobrecarga progressiva de 2.5% por semana na carga é o padrão ouro para ganhos sustentados de força e hipertrofia. Aumentos maiores ou menores reduzem a eficiência adaptativa.",
    },
    "fonseca_2014": {
        "modulo": "Treino",
        "badge_color": "#4ECDC4",
        "apa": (
            "Fonseca, R. M., Roschel, H., Tricoli, V., de Souza, E. O., Wilson, J. M., Laurentino, G. C., "
            "... & Ugrinowitsch, C. (2014). "
            "Changes in exercises are more effective than in loading schemes to improve muscle "
            "strength. Journal of Strength and Conditioning Research, 28(11), 3085–3092."
        ),
        "resumo": "Variação de exercícios (não apenas de cargas) promove maiores ganhos de força e hipertrofia. Rotação de exercícios dentro de grupos musculares mantém o estímulo adaptativo elevado.",
    },
    "helms_2014_treino": {
        "modulo": "Treino",
        "badge_color": "#4ECDC4",
        "apa": (
            "Helms, E. R., Fitschen, P. J., Aragon, A., Cronin, J., & Schoenfeld, B. J. (2014). "
            "Recommendations for natural bodybuilding contest preparation: resistance and "
            "cardiovascular training. Journal of Sports Medicine and Physical Fitness, 55(3), 164–178."
        ),
        "resumo": "Cutting: manter intensidade alta (8 reps pesadas, RIR 0-1) e reduzir volume em ~30–40% para preservar força. Descanso de 90–120s preserva potência relativa.",
    },

    # ─── RECUPERAÇÃO / VFC ──────────────────────────────────────────────────────
    "flatt_2016": {
        "modulo": "Recuperação",
        "badge_color": "#FFD166",
        "apa": (
            "Flatt, A. A., & Esco, M. R. (2016). "
            "Evaluating individual training adaptation with smartphone-derived heart rate variability "
            "in a collegiate swimming team. Journal of Strength and Conditioning Research, 30(2), 378–385."
        ),
        "resumo": "CV da VFC > 10% nos últimos 7 dias indica instabilidade autonômica e sobrecarga não adaptada. Atletas com CV elevado respondem melhor a reduções de volume que de intensidade.",
    },
    "jamieson_2009": {
        "modulo": "Recuperação",
        "badge_color": "#FFD166",
        "apa": (
            "Jamieson, J. (2009). "
            "Ultimate MMA Conditioning. "
            "Performance Sports Inc."
        ),
        "resumo": "Protocolo de recuperação por VFC: queda de 7–15% na VFC indica recuperação incompleta do SNC → apenas cardio Zona 2. Queda >15% indica fadiga severa → descanso total.",
    },
    "kiviniemi_2007": {
        "modulo": "Recuperação",
        "badge_color": "#FFD166",
        "apa": (
            "Kiviniemi, A. M., Hautala, A. J., Kinnunen, H., & Tulppo, M. P. (2007). "
            "Endurance training guided individually by daily heart rate variability measurements. "
            "European Journal of Applied Physiology, 101(6), 743–751."
        ),
        "resumo": "Treino guiado por VFC diária resulta em maiores ganhos de VO2max e potência que periodização fixa. VFC elevada = dia de alta intensidade; VFC reduzida = recuperação ativa.",
    },
    "gabbett_2016": {
        "modulo": "Recuperação",
        "badge_color": "#FFD166",
        "apa": (
            "Gabbett, T. J. (2016). "
            "The training-injury prevention paradox: should athletes be training smarter and harder? "
            "British Journal of Sports Medicine, 50(5), 273–280."
        ),
        "resumo": "ACWR entre 0.8–1.3 é a zona verde de segurança e performance. ACWR > 1.5 aumenta risco de lesão em 2–4x. ACWR < 0.8 indica destreinamento (perda de adaptações).",
    },
    "hulin_2016": {
        "modulo": "Recuperação",
        "badge_color": "#FFD166",
        "apa": (
            "Hulin, B. T., Gabbett, T. J., Lawson, D. W., Caputi, P., & Sampson, J. A. (2016). "
            "The acute:chronic workload ratio predicts injury: high chronic workload may decrease "
            "injury risk in elite rugby league players. British Journal of Sports Medicine, 50(4), 231–236."
        ),
        "resumo": "Confirma que carga crônica alta protege contra lesões (atletas condicionados toleram picos de ACWR maiores). Monitoramento contínuo é essencial para atletas de alto volume.",
    },

    # ─── SUPLEMENTAÇÃO ──────────────────────────────────────────────────────────
    "kreider_2017": {
        "modulo": "Suplementação",
        "badge_color": "#A8DADC",
        "apa": (
            "Kreider, R. B., Kalman, D. S., Antonio, J., Ziegenfuss, T. N., Wildman, R., Collins, R., "
            "... & Lopez, H. L. (2017). "
            "International Society of Sports Nutrition position stand: safety and efficacy of "
            "creatine supplementation in exercise, sport, and medicine. "
            "Journal of the International Society of Sports Nutrition, 14(1), 18."
        ),
        "resumo": "Creatina monohidratada: 3–5g/dia sem fase de carga. Grau A de evidência. Aumenta potência, volume de treino e síntese de glicogênio muscular. Segura para uso contínuo.",
    },
    "grgic_2019": {
        "modulo": "Suplementação",
        "badge_color": "#A8DADC",
        "apa": (
            "Grgic, J., Grgic, I., Pickering, C., Schoenfeld, B. J., Bishop, D. J., & Pedisic, Z. (2019). "
            "Wake up and smell the coffee: caffeine supplementation and exercise performance—an "
            "umbrella review of 21 published meta-analyses. British Journal of Sports Medicine, 54(11), 681–688."
        ),
        "resumo": "Cafeína 3–6mg/kg, 60min pré-treino: melhora força, resistência muscular e percepção de esforço. Meta-análise de meta-análises — maior nível de evidência disponível.",
    },
    "hobson_2012": {
        "modulo": "Suplementação",
        "badge_color": "#A8DADC",
        "apa": (
            "Hobson, R. M., Saunders, B., Ball, G., Harris, R. C., & Sale, C. (2012). "
            "Effects of β-alanine supplementation on exercise performance: a meta-analysis. "
            "Amino Acids, 43(1), 25–37."
        ),
        "resumo": "Beta-alanina 3.2–6.4g/dia aumenta carnosina muscular, tamponando acidose. Benefício significativo para exercícios de 1–4 minutos (séries de 8–20 reps com alto volume).",
    },
    "wilson_2014": {
        "modulo": "Suplementação",
        "badge_color": "#A8DADC",
        "apa": (
            "Wilson, J. M., Lowery, R. P., Joy, J. M., Andersen, J. C., Wilson, S. M. C., Stout, J. R., "
            "... & Rathmacher, J. (2014). "
            "The effects of 12 weeks of beta-hydroxy-beta-methylbutyrate free acid supplementation "
            "on muscle mass, strength, and power in resistance-trained individuals: a randomized, "
            "double-blind, placebo-controlled study. "
            "European Journal of Applied Physiology, 114(6), 1217–1227."
        ),
        "resumo": "HMB-FA (forma livre): anti-catabolismo significativo em cutting severo e peak week. 3g/dia reduz degradação proteica em períodos de déficit calórico agressivo.",
    },
}

# Referências agrupadas por módulo para exibição no painel
def get_refs_por_modulo(modulo: str) -> list:
    return [v for v in REFERENCIAS.values() if v["modulo"] == modulo]

def get_todas_refs() -> list:
    return list(REFERENCIAS.values())