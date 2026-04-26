# Dashboard: Imóvel vs. Carteira Diversificada

Dashboard interativo para análise comparativa de investimento em imóvel residencial vs. carteira diversificada de FIIs, ações e renda fixa.

## Stack

- **Streamlit** — UI e interatividade
- **Plotly** — gráficos interativos
- **Pandas / NumPy** — engine de simulação

## Estrutura

```
dashboard/
├── app.py              # Entry point Streamlit
├── config.py           # Parâmetros + dataclasses (RealEstate, Portfolio, Benchmark, Macro)
├── models.py           # Engine de simulação financeira
├── charts.py           # Geradores de gráficos Plotly
├── data_sources/
│   └── bcb.py          # Cliente HTTP da API SGS do Banco Central
├── services/
│   └── macro.py        # Cache + fallback dos indicadores macro
├── tests/              # Suíte pytest (test_bcb, test_macro, test_models)
├── requirements.txt
└── requirements-dev.txt
```

## Setup

```bash
cd dashboard
python -m venv .venv
source .venv/bin/activate              # ou .venv\Scripts\activate no Windows
pip install -r requirements.txt
streamlit run app.py
```

Acesse `http://localhost:8501` no navegador.

## Funcionalidades

- **Visão Geral**: KPIs, evolução do patrimônio, renda mensal, mapa risco × retorno
- **Imóvel**: decomposição waterfall de receita/custos, breakdown de custos anuais, custos de aquisição, financiamento opcional (SAC/Price) com saldo devedor e alerta de fluxo negativo
- **Carteira**: alocação por classe (donut), yields comparados, aporte mensal opcional indexado pelo IPCA
- **Sensibilidade**: tornado chart com variação de 6 parâmetros-chave
- **Tributação**: comparação direta de carga tributária efetiva
- **Risco (Monte Carlo)**: análise estocástica com 10.000 trajetórias, banda p10/p50/p90, drawdown máximo, probabilidade de bater meta de patrimônio
- **Exportar**: download da simulação completa em CSV

## Parâmetros configuráveis

Todos os parâmetros são editáveis via sidebar:

- Capital inicial, horizonte, reinvestimento
- Imóvel: aluguel, valorização, IPTU, vacância, adm, IR
- Carteira: pesos e yields por classe (FIIs papel/tijolo, Ações BR, Aristocrats US, RF)
- Benchmark: Taxa Selic

## Premissas macro (Abril/2026)

- Selic: 14,75% a.a.
- IPCA esperado: 4,80%
- CDI: 14,65%
- USD/BRL: 5,30
- DY médio IFIX: 11,80%

## Dados macro ao vivo

Os indicadores Selic, IPCA, CDI e USD/BRL são buscados ao vivo da API SGS do Banco Central, com cache de 24h. Em caso de falha (timeout, indisponibilidade), o app usa valores de referência hardcoded e exibe banner de aviso. Os sliders de macro permanecem editáveis para simulação de cenários.

## Financiamento imobiliário

O cenário Imóvel aceita um modo financiado opcional via toggle na sidebar:

- **Sistemas**: SAC (parcelas decrescentes) ou Price (parcelas fixas)
- **Inputs**: entrada (10–80%), prazo (5–35 anos), taxa anual (6–18%)
- **Sobra de capital**: a parte do capital inicial não usada na entrada vai para uma carteira interna do Imóvel, com o mesmo retorno total da Carteira diversificada
- **Cash flow mensal**: aluguel líquido − parcela − seguro entra (ou sai) da carteira interna
- **Alerta visual**: se a carteira interna ficar negativa, banner informa o ano em que cruzou zero

Quando o toggle está desligado, comportamento é idêntico ao Phase 1 (compra à vista).

## Análise de risco (Monte Carlo)

Camada estocástica paralela ao caminho determinístico:

- **N=10.000 trajetórias** com seed fixa (42) → resultado reproduzível.
- **Carteira**: cada classe de ativo tem σ próprio (FIIs ~14-16%, Ações BR ~27%, Aristocrats US ~18%, RF ~5%). Sliders na sidebar permitem sobrescrever.
- **Imóvel**: σ na valorização anual (default 10%). Aluguel cresce com a apreciação sorteada.
- **Imóvel financiado**: parcela continua determinística (taxa contratual fixa); carteira interna usa retorno blended estocástico da Carteira.
- **Aba "🎲 Risco"**: KPIs de probabilidade de bater meta, drawdown médio, percentis p10/p50/p90 do ano final, e histograma da distribuição final.
- **Visão Geral**: gráfico de patrimônio combina banda sombreada (estocástica) + linhas tracejadas (determinístico).

Limitações documentadas: distribuição normal (caudas finas) e ativos independentes (superestima diversificação). Migrações futuras (t-Student, matriz de correlação, VaR/CVaR) ficam para Phase 3.

## Observação

Modelo determinístico — não captura variância dos retornos. Para análise estocástica (Monte Carlo), expandir `models.py` com `numpy.random` e simulação por trajetória.
