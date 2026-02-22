# 🧬 Pro Coach IA — Periodização Científica IFBB Pro

Sistema de periodização e autorregulação para atletas de fisiculturismo competitivo, com recomendações baseadas em literatura científica peer-reviewed.

---

## 📁 Estrutura do Projeto

```
bodybuilding_coach/
├── app.py                  # Interface principal (Streamlit)
├── calculos_fisio.py       # Lógica de cálculos fisiológicos
├── references.py           # Banco de referências científicas (APA)
├── banco_exercicios.json   # Banco com 188 exercícios
├── requirements.txt        # Dependências do projeto
├── .gitignore              # Ignora data/, .venv/, secrets etc.
├── README.md               # Este arquivo
└── data/                   # Gerada automaticamente — NÃO commitada
    ├── .gitkeep            # Mantém a pasta no repositório
    └── registros_atleta.csv  # Criado após o 1º registro (ignorado pelo Git)
```

---

## 🚀 Deploy no Streamlit Community Cloud (Gratuito)

### Pré-requisitos
- Conta no [GitHub](https://github.com) (gratuita)
- Conta no [Streamlit Cloud](https://share.streamlit.io) (gratuita, login com GitHub)

---

### Passo 1 — Criar o repositório no GitHub

1. Acesse [github.com](https://github.com) e clique em **"New repository"**
2. Dê um nome ao repositório, ex: `bodybuilding-coach`
3. Deixe como **Public** (necessário para o plano gratuito do Streamlit Cloud)
4. Clique em **"Create repository"**

---

### Passo 2 — Enviar os arquivos para o GitHub

Se você tem o Git instalado, abra o terminal na pasta do projeto e rode:

```bash
git init
git add .
git commit -m "Initial commit — Pro Coach IA"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/bodybuilding-coach.git
git push -u origin main
```

**Substituia `SEU_USUARIO` pelo seu usuário do GitHub.**

Se preferir sem terminal, na página do repositório recém-criado clique em **"uploading an existing file"** e arraste todos os arquivos do projeto.

---

### Passo 3 — Deploy no Streamlit Cloud

1. Acesse [share.streamlit.io](https://share.streamlit.io)
2. Clique em **"New app"**
3. Preencha os campos:
   - **Repository:** `SEU_USUARIO/bodybuilding-coach`
   - **Branch:** `main`
   - **Main file path:** `app.py`
4. Clique em **"Deploy!"**
5. Aguarde ~2 minutos enquanto o ambiente é montado

Pronto. Você receberá uma URL pública no formato:
```
https://seu-usuario-bodybuilding-coach-app-XXXX.streamlit.app
```

Essa URL funciona em **qualquer browser**, em qualquer dispositivo (Android, iPhone, Windows, Mac, Linux) — sem instalar nada.

---

### Passo 4 — Persistência de dados (importante)

> ⚠️ O Streamlit Cloud **não persiste arquivos** entre sessões por padrão. Isso significa que o `registros_atleta.csv` pode ser resetado em deploys futuros.

**Solução recomendada para persistência real:** usar o `st.session_state` ou uma das opções abaixo:

#### Opção A — Google Sheets (mais fácil, gratuito)
Substitui o CSV por uma planilha Google como banco de dados.
Instale: `gsheets-connection` e configure via `st.connection`.

#### Opção B — Supabase (PostgreSQL gratuito na nuvem)
```bash
pip install supabase
```
Cria uma tabela `registros_atleta` e substitui as funções `carregar_registros()` e `salvar_registro()` por chamadas à API do Supabase.

#### Opção C — SQLite local + repositório (para uso pessoal)
Commitar o CSV manualmente após cada sessão. Funciona, mas é manual.

---

## 💻 Rodar Localmente

### Instalação

```bash
# Clone o repositório
git clone https://github.com/SEU_USUARIO/bodybuilding-coach.git
cd bodybuilding-coach

# Crie um ambiente virtual (recomendado)
python -m venv .venv

# Ative o ambiente virtual
# Linux / Mac:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate

# Instale as dependências
pip install -r requirements.txt
```

### Executar

```bash
streamlit run app.py
```

O app abrirá automaticamente em `http://localhost:8501`

---

## 🔄 Atualizar o App após Mudanças

Sempre que modificar os arquivos, envie para o GitHub:

```bash
git add .
git commit -m "Descrição da mudança"
git push
```

O Streamlit Cloud detecta automaticamente o push e faz **redeploy em ~1 minuto**.

---

## 📱 Usar no Celular

Após o deploy, acesse a URL do Streamlit Cloud pelo browser do celular (Chrome, Safari). Para uma experiência mais próxima de app nativo:

- **Android (Chrome):** Menu → "Adicionar à tela inicial" → vira um ícone na home
- **iPhone (Safari):** Compartilhar → "Adicionar à Tela de Início" → vira um ícone na home

---

## 🔬 Base Científica

Todas as recomendações do sistema são baseadas em literatura peer-reviewed. As referências completas estão disponíveis no painel **"📚 Base Científica Completa"** dentro do app, organizadas por módulo:

| Módulo | Referências-chave |
|---|---|
| Periodização | Rhea et al. (2002); Miranda et al. (2011); Peos et al. (2019) |
| Nutrição | Helms et al. (2014); Morton et al. (2018); Trexler et al. (2014) |
| Treino | Israetel et al. (2019); Zourdos et al. (2016); Ralston et al. (2017) |
| Recuperação | Flatt & Esco (2016); Gabbett (2016); Kiviniemi et al. (2007) |
| Suplementação | Kreider et al. (2017); Grgic et al. (2019); Hobson et al. (2012) |

---

## ⚕️ Aviso Legal

Este sistema é uma ferramenta de suporte educacional e de planejamento. Não substitui a avaliação de profissionais de educação física, nutrição e medicina. Consulte sempre um especialista certificado.