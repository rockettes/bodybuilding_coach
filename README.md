# 🏆 Bodybuilding Coach — Documentação Completa

> Aplicação Streamlit de coaching de fisiculturismo baseada em evidências científicas.  
> Stack: Python · Streamlit · Supabase · Plotly · `calculos_fisio.py`

---

## Índice

1. [Visão Geral](#visão-geral)
2. [Arquitetura](#arquitetura)
3. [Configuração e Deploy](#configuração-e-deploy)
4. [Glossário Completo](#glossário-completo)
5. [Níveis de Evidência](#níveis-de-evidência)
6. [Documentação das Abas](#documentação-das-abas)
7. [Fórmulas e Equações](#fórmulas-e-equações)
8. [Schema do Banco de Dados](#schema-do-banco-de-dados)
9. [Referências Científicas](#referências-científicas)

---

## Visão Geral

O **Bodybuilding Coach** é um sistema de coaching individual para atletas de fisiculturismo competitivo. Integra dados fisiológicos de wearables (Garmin), medidas corporais e dados de treino para gerar recomendações personalizadas de nutrição, volume de treino e recuperação — todas fundamentadas em literatura científica peer-reviewed.

**Categorias suportadas:** Mens Physique · Classic Physique · Bodybuilding Open · Bikini · Wellness · Physique Feminino

---

## Arquitetura

```
app.py                  → Interface Streamlit (11 abas)
calculos_fisio.py       → Engine de cálculos fisiológicos
requirements.txt        → Dependências Python

Banco de dados (Supabase / PostgreSQL):
  ├── perfil_atleta     → Dados do atleta e objetivos
  └── medidas_atleta    → Todos os registros (unified log)
```

**Fonte única de verdade:** todos os dados de um dia (peso, BF%, dobras, circunferências, recuperação, BIA avançada) ficam em uma única linha na tabela `medidas_atleta`. Todos os campos são opcionais — registre o que tiver disponível.

---

## Configuração e Deploy

### Pré-requisitos

```
Python 3.10+
Conta Supabase (gratuita)
Conta Streamlit Cloud (gratuita)
```

### Variáveis de ambiente (Streamlit Secrets)

```toml
# .streamlit/secrets.toml
SUPABASE_URL = "https://xxxx.supabase.co"
SUPABASE_KEY = "eyJ..."
```

### SQL de inicialização (Supabase)

Execute no SQL Editor do Supabase:

```sql
-- Tabela de perfil do atleta
CREATE TABLE IF NOT EXISTS perfil_atleta (
  id             uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id        text UNIQUE NOT NULL,
  nome           text,
  data_nasc      date,
  sexo           text DEFAULT 'Masculino',
  altura         float,
  anos_treino    integer DEFAULT 5,
  categoria      text DEFAULT 'Mens Physique',
  uso_peds       boolean DEFAULT false,
  bf_alvo        float DEFAULT 5.0,
  peso_alvo      float,
  cintura_alvo   float,
  ombros_alvo    float,
  coxa_alvo      float,
  data_competicao date,
  vfc_baseline   float DEFAULT 60.0,
  zona1_min integer, zona1_max integer,
  zona2_min integer, zona2_max integer,
  zona3_min integer, zona3_max integer,
  zona4_min integer, zona4_max integer,
  zona5_min integer, zona5_max integer,
  updated_at timestamptz
);

-- Tabela unificada de registros diários
CREATE TABLE IF NOT EXISTS medidas_atleta (
  id                  uuid DEFAULT gen_random_uuid() PRIMARY KEY,
  user_id             text NOT NULL,
  data                date NOT NULL,
  hora_registro       time,
  peso                float,
  bf_bioimpedancia    float,
  bf_formula          text,
  bf_calculado        float,
  bf_final            float,
  massa_gordura       float,
  massa_livre_gordura float,
  agua_total          float,
  agua_intracelular   float,
  agua_extracelular   float,
  angulo_fase         float,
  resistencia         float,
  reactancia          float,
  dobra_peitoral      float,
  dobra_axilar        float,
  dobra_tricipital    float,
  dobra_subescapular  float,
  dobra_abdominal     float,
  dobra_suprailiaca   float,
  dobra_coxa          float,
  dobra_bicipital     float,
  cintura             float,
  ombros              float,
  peito               float,
  quadril             float,
  biceps_d            float,
  coxa_d              float,
  panturrilha_d       float,
  pescoco             float,
  carga_treino        float,
  vfc_noturna         float,
  sleep_score         integer,
  recovery_time       integer,
  fc_repouso          integer,
  notas               text,
  created_at          timestamptz DEFAULT now()
);
```

---

## Glossário Completo

### Composição Corporal

| Termo | Sigla | Definição |
|-------|-------|-----------|
| **Body Fat** | BF% | Percentual de gordura corporal em relação ao peso total |
| **Fat Mass** | FM | Massa de gordura em kg: `FM = Peso × (BF% / 100)` |
| **Fat-Free Mass** | FFM | Massa livre de gordura (massa magra total) em kg: `FFM = Peso − FM` |
| **Lean Body Mass** | LBM | Sinônimo de FFM — músculo, osso, água, órgãos. Base de cálculo das recomendações de proteína |
| **Dobra cutânea** | — | Medida em mm de uma prega de pele + tecido adiposo subcutâneo com plicômetro |
| **Densidade corporal** | Dc | Valor intermediário das equações de dobras antes de converter para BF% pela equação de Siri |

### Bioimpedância Elétrica (BIA)

| Termo | Sigla | Definição |
|-------|-------|-----------|
| **Bioelectrical Impedance Analysis** | BIA | Método de estimativa de composição corporal que passa corrente elétrica de baixa intensidade pelo corpo |
| **Resistência** | R (Ω) | Oposição da água corporal ao fluxo de corrente. Aumenta com desidratação. Atletas: 380–450 Ω típico |
| **Reactância** | Xc (Ω) | Oposição das membranas celulares ao fluxo de corrente. Reflete integridade e quantidade celular. Atletas: 60–80 Ω |
| **Ângulo de Fase** | PhA (°) | Indicador de saúde celular derivado de R e Xc via arctan. Atletas de elite: ≥ 7°; bodybuilders show-day: 9.3–11.2° |
| **Água Total** | TBW | Total Body Water — soma de toda a água corporal (L). `TBW = ICW + ECW` |
| **Água Intracelular** | ICW | Intracellular Water — água dentro das células. Correlaciona com massa muscular funcional |
| **Água Extracelular** | ECW | Extracellular Water — água fora das células (plasma, linfa, interstício). Alta ECW = retenção visível |
| **Razão ICW/ECW** | — | Indicador crítico na Peak Week. Alvo no dia do show: ≥ 1.90 *(Ribas et al., 2022)* |

### Volume de Treino

| Termo | Sigla | Definição |
|-------|-------|-----------|
| **Minimum Effective Volume** | MEV | Volume mínimo de séries por músculo por semana para **manter** adaptações. Abaixo do MEV há destreino |
| **Maximum Adaptive Volume** | MAV | Volume máximo que gera adaptação sem comprometer recuperação. É o **alvo de treino** da fase de hipertrofia |
| **Maximum Recoverable Volume** | MRV | Volume máximo que o corpo consegue recuperar. Acima do MRV ocorre overreaching e regressão |
| **Reps in Reserve** | RIR | Repetições que "sobram" antes da falha concêntrica. RIR 0 = falha; RIR 2 = poderia fazer mais 2 reps |
| **Volume Load** | — | Carga total de treino: `Séries × Repetições × Carga (kg)` — base do cálculo de ACWR |
| **Overreaching** | — | Estado de fadiga acumulada que supera a capacidade de recuperação. Pode ser funcional (intencional, curto prazo) ou não-funcional (acidental, semanas a meses) |

### Cardio e Zonas de FC

| Termo | Sigla | Definição |
|-------|-------|-----------|
| **Low-Intensity Steady State** | LISS | Cardio contínuo de baixa intensidade (Zona 2, 60–70% FCmáx) por 30–60 min. Ideal para oxidação de gordura sem prejudicar recuperação muscular. Preferido no cutting |
| **High-Intensity Interval Training** | HIIT | Cardio intervalado de alta intensidade (Zona 4–5, ≥ 85% FCmáx). Eficiente em tempo mas com maior custo de recuperação do SNC. Usar com moderação no cutting |
| **FC Máxima** | FCmáx | Frequência cardíaca máxima estimada: `208 − 0.7 × idade` *(Tanaka et al., 2001)* |
| **FC Repouso** | FCr | FC medida em repouso absoluto (ao acordar). Marcador de recuperação e base do cálculo de Karvonen |
| **FC de Reserva** | FCR | `FCR = FCmáx − FCr`. Quanto maior, maior a amplitude de trabalho cardiovascular disponível |
| **Método Karvonen** | — | Prescrição de FC de treino baseada na FC de reserva, mais individualizada que % simples de FCmáx |

### Recuperação e VFC

| Termo | Sigla | Definição |
|-------|-------|-----------|
| **Variabilidade da Frequência Cardíaca** | VFC | Variação em ms entre batimentos cardíacos consecutivos. Alta VFC = boa recuperação do Sistema Nervoso Autônomo |
| **Sistema Nervoso Central** | SNC | Cérebro + medula espinhal. Treino intenso gera fadiga central, refletida em queda da VFC |
| **Coeficiente de Variação da VFC** | CV-VFC | Variabilidade da VFC ao longo de 7 dias como % da média. CV ≤ 7% = estável; > 10% = sobrecarga |
| **Acute:Chronic Workload Ratio** | ACWR | Razão carga aguda (7 dias) / carga crônica (28 dias). Zona ótima: 0.8–1.3 *(Gabbett, 2016)* |
| **Sleep Score** | — | Pontuação 0–100 de qualidade do sono fornecida por wearables Garmin. Inclui duração, fases e movimentos noturnos |
| **Recovery Time** | — | Tempo estimado em horas pelo Garmin antes do próximo treino intenso, baseado em VFC e carga recente |

### Nutrição e Metabolismo

| Termo | Sigla | Definição |
|-------|-------|-----------|
| **Taxa Metabólica Basal** | TMB | Energia mínima para manutenção das funções vitais em repouso absoluto (kcal/dia) |
| **Gasto Energético Total** | GET | TMB × fator de atividade física. Representa o gasto calórico real diário |
| **Termogênese Adaptativa** | TA | Redução do metabolismo em resposta a déficit calórico prolongado. Sistema aplica −15 kcal/semana após 4 semanas em déficit, máx −200 kcal *(Trexler et al., 2014)* |
| **Refeed** | — | Dia(s) com calorias na manutenção ou acima durante o cutting, para restaurar leptina, glicogênio e metabolismo |
| **Carb-Up / Loading** | — | Protocolo Peak Week com 8 g/kg/dia de carboidratos (dias 4–5) para supercompensação de glicogênio muscular |
| **Leptina** | — | Hormônio da saciedade produzido pelo tecido adiposo. Cai em déficit calórico, aumentando fome e reduzindo metabolismo. Refeeds restauram temporariamente |
| **Superávit calórico** | — | Calorias acima do GET. Bulking: +300 kcal (naturais) ou +500 kcal (PEDs) |
| **Déficit calórico** | — | Calorias abaixo do GET. Cutting: −500 kcal base |

### Periodização

| Termo | Definição |
|-------|-----------|
| **Bulking** | Fase de ganho de massa com superávit calórico controlado. Objetivo: maximizar síntese de LBM com ganho mínimo de FM |
| **Cutting** | Fase de perda de gordura com déficit calórico. Objetivo: preservar LBM enquanto reduz FM e BF% |
| **Recomposição Corporal** | Ganho simultâneo de LBM e perda de FM. Possível em iniciantes, retornantes e usuários de PEDs |
| **Peak Week** | Última semana antes da competição. Depleção (dias 1–3) + supercompensação de glicogênio (dias 4–5) |
| **Off-Season** | Período pós-competição de recuperação antes de iniciar novo ciclo |
| **Platô Metabólico** | Taxa de perda < 0.5%/semana por ≥ 2 semanas durante cutting. Indica adaptação metabólica |
| **PEDs** | Performance-Enhancing Drugs — recursos ergogênicos farmacológicos. Alteram as recomendações de proteína, superávit e taxas de ganho |

### Proporções Estéticas

| Termo | Definição |
|-------|-----------|
| **Razão Áurea** | φ = 1.618. Proporção matemática considerada o padrão estético ideal na relação ombro/cintura |
| **Razão Ombro/Cintura** | Circunferência de ombros ÷ cintura. Alvo: ≥ φ = 1.618 |
| **V-Taper** | Silhueta em "V" — ombros largos com cintura estreita. Criterio principal em Mens Physique e Classic Physique |

---

## Níveis de Evidência

### Grau A — Evidência Forte

> Baseado em múltiplos estudos controlados randomizados (RCTs) ou meta-análises de alta qualidade. Consenso científico estabelecido.

**Exemplos no app:**
- Proteína 2.2–3.1 g/kg LBM preserva massa magra no cutting *(Helms et al., 2014)*
- ACWR 0.8–1.3 como zona de baixo risco *(Gabbett, 2016)*
- Taxa de perda 0.5–1.0%/semana maximiza retenção de LBM *(Helms et al., 2014)*
- Supercompensação de glicogênio na Peak Week *(Chappell et al., 2018)*

### Grau B — Evidência Moderada

> Baseado em estudos observacionais de qualidade, estudos caso-controle, ou RCTs com limitações. Plausibilidade fisiológica forte.

**Exemplos no app:**
- VFC como marcador de recuperação do SNC *(Flatt & Esco, 2016)*
- Ângulo de fase > 9.6° em bodybuilders no show *(Ribas et al., 2022)*
- Taxas de ganho ótimas por nível de experiência *(Iraki et al., 2019)*
- MEV/MAV/MRV por grupo muscular *(Israetel et al., 2019)*
- Termogênese adaptativa *(Trexler et al., 2014)*

### Como ler as citações no app

```
*(Autor et al., Ano)*       → referência disponível na aba 📚 Referências
*(PMCxxxxxxx)*              → PubMed Central ID para acesso ao artigo completo
```

---

## Documentação das Abas

### 🏠 Dashboard

Visão geral do dia atual com todos os indicadores em um único painel.

| Painel | Conteúdo |
|--------|----------|
| Métricas de cabeçalho | Fase atual, dias para o show, próxima fase (com dias até ela), taxa de perda semanal, peso atual, BF% atual |
| Status de Recuperação | Calculado a partir de VFC, sleep score e recovery time. Requer ao menos um desses campos registrado |
| Alvo Nutricional | Macros do dia (calorias, proteína, carboidrato, gordura) para a fase corrente |
| Atual vs. Objetivo | Tabela com valores atuais, objetivos e delta (Δ) para: Peso, BF%, Cintura, Ombros, Coxa D |
| Proporções Estéticas | Barra de progresso Ombro/Cintura e status de todas as proporções da categoria |

**Lógica de objetivos (hierarquia):**

```
1. Manual (configurado na aba Perfil)         ← prioridade máxima
2. Calculado automaticamente:
   Cintura alvo = Ombros_atuais / φ   (ou Altura × pct_categoria)
   Ombros alvo  = Cintura_alvo × φ
   Peso alvo    = LBM_atual / (1 - BF%_alvo / 100)
   Coxa alvo    = Altura × 0.52–0.55 (por categoria)
```

---

### 🗓️ Periodização

Planejamento das fases do ciclo de preparação com detecção automática de fase.

**Cálculo automático de fases:**

```
Data da competição (D)
  D - 7 dias   = início Peak Week
  D - 119 dias = início Cutting (17 semanas)
  Antes disso  = Bulking (se BF < limite) ou Recomposição
```

**Limites de BF% para início do bulking:**
- Masculino: BF% < 15% (acima → Recomposição primeiro)
- Feminino: BF% < 22%

**Detecção de platô:** taxa de perda < 0.5%/semana por ≥ 2 semanas.

$$\text{Taxa}_{\%/sem} = \frac{P_{-14\,dias} - P_{\text{hoje}}}{P_{-14\,dias}} \times \frac{100}{2}$$

---

### 🍽️ Nutrição

Plano alimentar semanal personalizado por fase, com macros diários e zonas de FC para o cardio.

**Estratégia por fase:**

| Fase | Estratégia | Déficit / Superávit |
|------|-----------|---------------------|
| Bulking | Superávit uniforme (7 dias) | +300 kcal (natural) · +500 kcal (PEDs) |
| Cutting | 5:2 — Low Carb (seg–sex) + Refeed (sáb–dom) | −500 kcal base |
| Recomposição | Leve déficit todos os dias | −200 kcal |
| Peak Week | Depleção (dias 1–3) → Carb-Up (dias 4–5) | Protocolo específico |

**Proteína por fase:**

| Fase | Dose | Fonte |
|------|------|-------|
| Bulking (natural) | 2.2 g/kg LBM | Iraki et al., 2019 |
| Bulking (PEDs) | 2.8 g/kg LBM | Iraki et al., 2019 |
| Cutting/Peak Week | 3.1 g/kg LBM | Helms et al., 2014 |
| Recomposição | 2.5 g/kg LBM | Barakat et al., 2020 |

**Fórmulas de macro (carboidrato por resíduo calórico):**

$$\text{CHO} = \frac{\text{Calorias}_{\text{alvo}} - (\text{Proteína} \times 4) - (\text{Gordura} \times 9)}{4}$$

**Peak Week — Carb-Up (dias 4–5):**

$$\text{CHO}_{loading} = \text{Peso} \times 8 \; \text{g/kg/dia}$$

---

### 🏋️ Treino

Volume semanal prescrito por fase, com RIR alvo e protocolo de progressão.

**Volumes de referência (séries/músculo/semana):**

| Fase | MEV | MAV | MRV |
|------|:---:|:---:|:---:|
| Bulking | 10 | **18** | 22 |
| Cutting | 6 | **10** | 14 |
| Peak Week | 4 | **7** | 10 |
| Recomposição | 8 | **14** | 18 |
| Off-Season | 4 | **8** | 12 |

> O **MAV** é o alvo atual. MEV = manter. MRV = limite superior nunca a ultrapassar.  
> *(Israetel et al., 2019 — grau B)*

**RIR por fase:**

| Fase | RIR | Interpretação |
|------|-----|--------------|
| Bulking | 1–2 | Treino intenso para máxima síntese proteica |
| Cutting | 0–1 | Manter intensidade para sinalizar preservação de LBM |
| Peak Week | 3–4 | Volume e intensidade reduzidos — evitar dano muscular excessivo |
| Recomposição | 1–2 | Equilíbrio entre estímulo e recuperação |

**Taxa de ganho ótima no Bulking** *(Iraki et al., 2019)*:

| Nível | Anos de treino | Taxa/semana |
|-------|---------------|-------------|
| Novato | ≤ 2 anos | 0.5% do peso corporal |
| Intermediário | 2–4 anos | 0.35% do peso corporal |
| Avançado | ≥ 5 anos | 0.25% do peso corporal |

Composição ideal do ganho: 60–65% LBM · 35–40% FM máximo.

---

### 🎯 Recuperação

Monitoramento da recuperação do SNC com base em VFC, sleep, ACWR e CV-VFC.

**Dados necessários** (registrar na aba 📁 Registros):
- `VFC Noturna` + `Sleep Score` + `Recovery Time` + `FC Repouso`
- Mínimo 7 registros para calcular ACWR e CV-VFC
- Mínimo 28 registros para ACWR com janela crônica completa

**ACWR:**

$$\text{ACWR} = \frac{\overline{\text{Volume Load}}_{7\,\text{dias}}}{\overline{\text{Volume Load}}_{28\,\text{dias}}}$$

| ACWR | Zona | Ação |
|:----:|------|------|
| < 0.8 | 🔵 Subtreino | Aumentar volume gradualmente |
| 0.8–1.3 | 🟢 Ótimo | Manter protocolo atual |
| 1.3–1.5 | 🟡 Atenção | Monitorar sinais de fadiga |
| > 1.5 | 🔴 Alto risco | Reduzir volume imediatamente |

**CV-VFC:**

$$\text{CV}_{VFC} = \frac{\sigma(\text{VFC}_{7\,\text{dias}})}{\mu(\text{VFC}_{7\,\text{dias}})} \times 100\%$$

| CV-VFC | Status |
|:------:|--------|
| ≤ 7% | 🟢 VFC estável — recuperação adequada |
| 7–10% | 🟡 VFC variável — atenção ao volume |
| > 10% | 🔴 VFC instável — sobrecarga ou doença? |

**Score de Fadiga Diária** (0–4 pontos):

| Condição | Pontos |
|---------|:------:|
| VFC < baseline (queda > 10%) | +1 |
| Sleep Score < 70 | +1 |
| Recovery Time > 48 h | +1 |
| ACWR > 1.5 **ou** CV-VFC > 10% | +1 |

| Score | Status | Prescrição |
|:-----:|--------|-----------|
| 0 | ✅ Recuperado | Treino normal conforme plano |
| 1 | 🟡 Atenção | Treino moderado, monitorar |
| 2 | 🟠 Fadiga Parcial | Reduzir volume 30% |
| ≥ 3 | 🔴 Fadiga Severa | Descanso ativo ou deload |

---

### 📁 Registros

Entrada unificada de todos os dados do dia. Um registro = uma linha temporal com todos os campos opcionais.

**Grupos de dados:**

1. **Composição Corporal (BIA)** — peso, BF% (bioimpedância / dobras / final), FM, FFM, TBW, ICW, ECW, ângulo de fase, R, Xc
2. **Recuperação** — Volume Load, VFC Noturna, Sleep Score, Recovery Time, FC Repouso
3. **Dobras Cutâneas (mm)** — 8 sítios: peitoral, axilar, tricipital, subescapular, abdominal, suprailiaca, coxa, bíceps
4. **Circunferências (cm)** — cintura, ombros, peito, quadril, bíceps D, coxa D, panturrilha D, pescoço

**BF% Final:** média automática de `bf_bioimpedancia` e `bf_calculado` (por dobras). Pode ser sobrescrito.

**ICW/ECW ratio:** calculado em tempo real ao preencher os campos de água. Codificação por cor:
- 🟢 ≥ 1.90 — alvo show-day
- 🟡 1.60–1.89 — zona intermediária
- 🔴 < 1.60 — retenção extracelular significativa

**Botão "📋 Último registro":** preenche todos os campos do grupo com os valores mais recentes.

**Seleção para edição:** clicar em qualquer linha do histórico carrega todos os valores no formulário para edição ou exclusão.

---

### 📊 Avaliação Semanal

Análise multi-objetivo da semana — compara o realizado com o esperado e sugere ajustes calóricos.

**Variáveis avaliadas simultaneamente:**
- Taxa de perda/ganho de peso vs. alvo da fase
- Variação de LBM vs. limite máximo de perda
- Variação de FM vs. trajetória esperada
- Variação de BF% vs. progressão necessária

**Detecção de conflito multi-objetivo:**  
Quando dois objetivos exigem ajustes calóricos opostos (ex: BF% subindo rápido no bulking enquanto o ganho está abaixo do alvo), o sistema exibe três opções estratégicas com os trade-offs de cada uma e deixa o atleta escolher a prioridade.

**Métricas exibidas:** Δ Peso · Δ LBM · Δ FM · Δ BF%

---

### 💊 Suplementação

Lista de suplementos com evidência grau A ou B para fisiculturismo competitivo.

**Critério de inclusão:** ao menos um estudo humano randomizado publicado em periódico indexado. Suplementos sem evidência sólida não são listados.

**Grau A — evidência forte:**

| Suplemento | Dose | Timing |
|-----------|------|--------|
| Creatina Monohidratada | 3–5 g/dia | Qualquer horário |
| Proteína Whey | Para completar alvo diário | Pós-treino e refeições |
| Cafeína | 3–6 mg/kg | 30–60 min pré-treino |
| β-Alanina | 3.2–6.4 g/dia (fracionado) | Com refeições (reduz formigamento) |

**Grau B — evidência moderada:**

| Suplemento | Dose | Timing |
|-----------|------|--------|
| Citrulina Malato | 6–8 g | 30–60 min pré-treino |
| Ômega-3 | 2–4 g EPA+DHA/dia | Com refeição gordurosa |
| Vitamina D3 | 2000–4000 UI/dia | Com refeição contendo gordura |
| Magnésio (Bisglicinato) | 200–400 mg | À noite |

---

### 📈 Evolução

Gráficos de evolução temporal separados por tipo de dado. Cada seção só aparece quando há dados suficientes registrados.

| # | Gráfico | Variáveis | Eixo duplo |
|---|---------|-----------|:---------:|
| 1 | Composição Corporal | Peso, BF% (bio/dobras/final), FM, FFM | ✅ kg vs % |
| 2 | Água Corporal | TBW, ICW, ECW (L) + ratio ICW/ECW | ✅ L vs ratio |
| 3 | Ângulo de Fase BIA | PhA (°), R (Ω), Xc (Ω) com faixa 7–12° | ✅ ° vs Ω |
| 4 | Dobras Cutâneas | 8 sítios individuais (mm) + soma total | ✅ mm vs soma |
| 5 | Circunferências | 7 medidas em cm | ❌ |
| 6 | Proporções Estéticas | Ombro/Cintura, Quadril/Cintura vs φ=1.618 | ❌ |
| 7 | Recuperação | VFC, Sleep, Recovery Time, FC Repouso, Volume Load | ✅ |

---

### 👤 Perfil

Configuração única do atleta. Dados salvos persistem entre sessões via Supabase.

**Dados Pessoais:** nome, data de nascimento (calcula idade automaticamente), sexo biológico, altura, anos de treino.

**Dados Competitivos:** categoria alvo, uso de PEDs, data da próxima competição, VFC baseline.

**Objetivos no Palco:** BF% alvo, peso alvo, cintura alvo, ombros alvo, coxa alvo.  
Deixe em 0 para cálculo automático baseado na Razão Áurea e BF% alvo.

**Zonas de FC:**
- **Modo automático:** calculado por Karvonen com FCmáx de Tanaka usando a FC repouso do último registro
- **Modo manual (ergoespirometria):** inserir zonas do laudo; Karvonen exibido ao lado para comparação

---

### 📚 Referências

Base científica completa das 30+ referências utilizadas nas recomendações, organizadas por módulo: Periodização · Nutrição · Treino · Recuperação · Suplementação.

---

## Fórmulas e Equações

### Equação de Siri (1956) — Densidade → BF%

$$\text{BF\%} = \left(\frac{495}{D_c}\right) - 450$$

### Jackson-Pollock 7 Dobras — Masculino *(JP7)*

$$D_c = 1.112 - 0.00043499 \cdot S_7 + 0.00000055 \cdot S_7^2 - 0.00028826 \cdot \text{Idade}$$

### Jackson-Pollock 7 Dobras — Feminino *(JP7)*

$$D_c = 1.097 - 0.00046971 \cdot S_7 + 0.00000056 \cdot S_7^2 - 0.00012828 \cdot \text{Idade}$$

$S_7$ = soma das 7 dobras em mm (peitoral + axilar + tricipital + subescapular + abdominal + suprailiaca + coxa)

### Jackson-Pollock 3 Dobras — Masculino *(JP3)*

$$D_c = 1.10938 - 0.0008267 \cdot S_3 + 0.0000016 \cdot S_3^2 - 0.0002574 \cdot \text{Idade}$$

$S_3$ = peitoral + abdominal + coxa (mm)

### Jackson-Pollock 3 Dobras — Feminino *(JP3 fem, Jackson et al., 1980)*

$$D_c = 1.0994921 - 0.0009929 \cdot S_3 + 0.0000023 \cdot S_3^2 - 0.0001392 \cdot \text{Idade}$$

$S_3$ = tricipital + suprailiaca + coxa (mm)

### Durnin & Womersley (1974) — 4 Dobras

$$D_c = C - M \times \log_{10}(S_4)$$

$S_4$ = bíceps + tríceps + subescapular + suprailiaca (mm)

Os coeficientes $C$ e $M$ variam por sexo e faixa etária (20–29, 30–39, 40–49, 50+). Mais precisa para BF% > 20%.

### TMB — Katch-McArdle

$$\text{TMB} = 370 + 21{,}6 \times \text{LBM}$$

$$\text{LBM} = \text{Peso} \times \left(1 - \frac{\text{BF\%}}{100}\right) \quad \text{(kg)}$$

> Vantagem sobre Harris-Benedict: usa a massa magra diretamente — mais precisa para atletas com BF% baixo.

### GET — Gasto Energético Total

$$\text{GET} = \text{TMB} \times \text{NAF}$$

NAF = 1.55 (moderadamente ativo — padrão do sistema).

### Termogênese Adaptativa *(Trexler et al., 2014)*

$$\text{Cal}_{\text{ajust}} = \text{Cal}_{\text{base}} - \min\!\Big((\text{semanas em déficit} - 4) \times 15,\; 200\Big)$$

Aplicado somente após 4 semanas contínuas em déficit calórico.

### FCmáx — Tanaka et al. (2001)

$$\text{FC}_{\text{máx}} = 208 - 0{,}7 \times \text{Idade}$$

> Mais precisa que a fórmula clássica (220 − idade) para adultos fisicamente ativos.

### FC de Treino — Método Karvonen

$$\text{FC}_{\text{treino}} = \left[(\text{FC}_{\text{máx}} - \text{FC}_{\text{repouso}}) \times I\%\right] + \text{FC}_{\text{repouso}}$$

Onde $I\%$ é a intensidade percentual desejada:

| Zona | Intensidade ($I\%$) | Finalidade |
|------|:-----------------:|-----------|
| 1 — Recuperação Ativa | 50–60% | Deload, dias leves |
| 2 — LISS / Fat-Burning | 60–70% | Cardio no cutting, oxidação de gordura |
| 3 — Aeróbio Moderado | 70–80% | Condicionamento geral |
| 4 — Limiar Anaeróbio | 80–90% | Capacidade aeróbia alta |
| 5 — HIIT / Máximo | 90–100% | Intervalos curtos de alta potência |

### Ângulo de Fase BIA *(Kyle et al., 2005)*

$$\text{PhA} = \arctan\!\left(\frac{X_c}{R}\right) \times \frac{180°}{\pi}$$

**Valores de referência:**

| Condição | PhA |
|---------|:---:|
| População geral | 5–7° |
| Atletas de resistência | ≥ 7° |
| Bodybuilders (offseason) | 9.3 ± 0.6° |
| Bodybuilders (show-day) | 9.6 ± 0.7° |

*(Ribas et al., 2022 — PMC8880471)*

### Razão ICW/ECW — Peak Week *(Ribas et al., 2022)*

| Momento | ICW/ECW | Significado |
|---------|:-------:|------------|
| Dia anterior ao show | ~1.60 | Fluido ainda extravascular |
| Dia do show (alvo) | ≥ 1.90 | Água migrou para o compartimento intracelular |

Protocolo de 11 bodybuilders masculinos: ICW ↑ 31.6 → 33.1 L · ECW ↓ 19.8 → 17.2 L · TBW ↓ 51.4 → 50.3 L

### Peso Alvo (preservando LBM)

$$\text{Peso}_{\text{alvo}} = \frac{\text{LBM}_{\text{atual}}}{1 - \dfrac{\text{BF\%}_{\text{alvo}}}{100}}$$

### Ombros Alvo pela Razão Áurea

$$\text{Ombros}_{\text{alvo}} = \text{Cintura}_{\text{alvo}} \times \varphi \qquad (\varphi = 1{,}618)$$

### ACWR

$$\text{ACWR} = \frac{\overline{\text{Volume Load}}_{7\,\text{dias}}}{\overline{\text{Volume Load}}_{28\,\text{dias}}}$$

### CV-VFC

$$\text{CV}_{VFC} = \frac{\sigma\!\left(\text{VFC}_{7\,\text{dias}}\right)}{\mu\!\left(\text{VFC}_{7\,\text{dias}}\right)} \times 100\%$$

---

## Schema do Banco de Dados

### Tabela `perfil_atleta`

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | uuid | Chave primária auto-gerada |
| `user_id` | text UNIQUE | ID do usuário (um perfil por conta) |
| `nome` | text | Nome do atleta |
| `data_nasc` | date | Data de nascimento |
| `sexo` | text | `'Masculino'` ou `'Feminino'` |
| `altura` | float | Altura em cm |
| `anos_treino` | integer | Anos de treinamento com pesos |
| `categoria` | text | Categoria competitiva alvo |
| `uso_peds` | boolean | Uso de PEDs / TRT |
| `bf_alvo` | float | % BF objetivo no palco |
| `peso_alvo` | float | Peso objetivo em kg (null = calculado) |
| `cintura_alvo` | float | Cintura objetivo em cm (null = calculado) |
| `ombros_alvo` | float | Ombros objetivo em cm (null = calculado) |
| `coxa_alvo` | float | Coxa objetivo em cm (null = calculado) |
| `data_competicao` | date | Data da próxima competição |
| `vfc_baseline` | float | VFC de referência em ms (média 7 dias) |
| `zona[1-5]_min/max` | integer | Zonas de FC personalizadas (ergoespirometria) |

### Tabela `medidas_atleta`

| Grupo | Colunas | Tipo |
|-------|---------|------|
| Identificação | `id`, `user_id`, `data`, `hora_registro` | uuid, text, date, time |
| Composição | `peso`, `bf_bioimpedancia`, `bf_formula`, `bf_calculado`, `bf_final`, `massa_gordura`, `massa_livre_gordura` | float |
| BIA Avançada | `agua_total`, `agua_intracelular`, `agua_extracelular`, `angulo_fase`, `resistencia`, `reactancia` | float |
| Dobras (mm) | `dobra_peitoral`, `dobra_axilar`, `dobra_tricipital`, `dobra_subescapular`, `dobra_abdominal`, `dobra_suprailiaca`, `dobra_coxa`, `dobra_bicipital` | float |
| Circunferências (cm) | `cintura`, `ombros`, `peito`, `quadril`, `biceps_d`, `coxa_d`, `panturrilha_d`, `pescoco` | float |
| Recuperação | `carga_treino`, `vfc_noturna`, `sleep_score`, `recovery_time`, `fc_repouso` | float/int |
| Notas | `notas` | text |

---

## Referências Científicas

| Referência | Tópico | Grau |
|-----------|--------|:----:|
| Jackson & Pollock (1978). *Med Sci Sports.* | Fórmulas JP7 e JP3 Masculino | A |
| Jackson, Pollock & Ward (1980). *Med Sci Sports.* | Fórmula JP3 Feminino | A |
| Durnin & Womersley (1974). *Br J Nutr.* | Fórmula 4 dobras | A |
| Siri (1956). *Body composition from fluid spaces and density.* | Equação Siri Dc → BF% | A |
| Tanaka, Monahan & Seals (2001). *J Am Coll Cardiol.* | FCmáx = 208 − 0.7×idade | A |
| Helms, Aragon & Fitschen (2014). *JISSN.* PubMed 24864135 | Proteína no cutting, taxa de perda | A |
| Gabbett (2016). *Br J Sports Med.* | ACWR e risco de lesão | A |
| Chappell et al. (2018). *JISSN.* | Peak Week — depleção e carb-up | A |
| Trexler et al. (2014). *JISSN.* | Termogênese adaptativa | B |
| Flatt & Esco (2016). *JSCR.* | VFC como marcador de recuperação do SNC | B |
| Iraki et al. (2019). *JISSN.* | Taxas de ganho ótimas por nível de experiência | B |
| Israetel, Hoffmann & CJ (2019). *Renaissance Periodization.* | MEV / MAV / MRV por grupo muscular | B |
| Ribas et al. (2022). *PMC8880471.* | BIA Peak Week — ICW/ECW e ângulo de fase | B |
| Kyle et al. (2005). *Clin Nutr.* | Valores de referência ângulo de fase | B |
| Barakat et al. (2020). *JISSN.* | Recomposição corporal | B |
| Peos et al. (2019). *JISSN.* | Platô metabólico no cutting | B |
| Flatt et al. (2018). *Int J Sports Physiol Perform.* | VFC 7 dias e prescrição de treino | B |
| Katch & McArdle (1975). | Equação TMB por massa magra | A |

---

*Documentação gerada a partir do código-fonte. Última atualização: fevereiro/2026.*