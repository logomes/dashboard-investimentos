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
├── config.py           # Parâmetros e constantes (dataclasses)
├── models.py           # Engine de simulação financeira
├── charts.py           # Geradores de gráficos Plotly
└── requirements.txt
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
- **Imóvel**: decomposição waterfall de receita/custos, breakdown de custos anuais, custos de aquisição
- **Carteira**: alocação por classe (donut), yields comparados, aporte mensal opcional indexado pelo IPCA
- **Sensibilidade**: tornado chart com variação de 6 parâmetros-chave
- **Tributação**: comparação direta de carga tributária efetiva
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

## Observação

Modelo determinístico — não captura variância dos retornos. Para análise estocástica (Monte Carlo), expandir `models.py` com `numpy.random` e simulação por trajetória.
