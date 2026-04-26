"""Streamlit dashboard for investment scenario comparison.

Usage:
    streamlit run app.py

Compares real estate vs diversified portfolio investment for a given capital,
with adjustable parameters and interactive Plotly charts.
"""

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from config import (
    BenchmarkParams,
    FinancingParams,
    MacroParams,
    MonteCarloParams,
    PALETTE,
    PortfolioParams,
    RealEstateParams,
    TODAY_LABEL,
)
from services.macro import get_macro_params
from models import (
    annual_tax_comparison,
    build_comparison_dataframe,
    build_schedule,
    MonteCarloResult,
    sensitivity_real_estate,
    simulate_benchmark,
    simulate_portfolio,
    simulate_portfolio_mc,
    simulate_real_estate,
    simulate_real_estate_mc,
    SimulationResult,
)
from charts import (
    annual_income_chart,
    cost_breakdown_chart,
    debt_evolution_chart,
    distribution_histogram_chart,
    income_vs_costs_waterfall,
    patrimony_band_chart,
    patrimony_evolution_chart,
    portfolio_donut_chart,
    risk_return_scatter,
    sensitivity_tornado_chart,
    tax_comparison_chart,
    yield_comparison_bars,
)


# ---------- Page configuration ----------

st.set_page_config(
    page_title="Imóvel vs. Carteira | Análise de Investimento",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------- Custom CSS ----------

st.markdown("""
<style>
    .main > div { padding-top: 1.5rem; }
    h1 { color: #1F3A5F; font-weight: 700; }
    h2 { color: #2C3E50; border-bottom: 2px solid #2980B9; padding-bottom: 0.4rem; }
    h3 { color: #34495E; }

    [data-testid="stMetricValue"] { font-size: 1.7rem; font-weight: 700; }
    [data-testid="stMetricLabel"] { font-size: 0.9rem; color: #7F8C8D; }
    [data-testid="stMetricDelta"] { font-size: 0.85rem; }

    .stTabs [data-baseweb="tab-list"] { gap: 8px; }
    .stTabs [data-baseweb="tab"] {
        background-color: #ECF0F1;
        border-radius: 6px 6px 0 0;
        padding: 10px 20px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background-color: #2980B9;
        color: white;
    }

    .info-card {
        background: linear-gradient(135deg, #F8F9FA 0%, #ECF0F1 100%);
        border-left: 4px solid #2980B9;
        padding: 1rem 1.4rem;
        border-radius: 6px;
        margin: 0.5rem 0;
    }
</style>
""", unsafe_allow_html=True)


# ---------- Sidebar: Parameters ----------

def render_sidebar(macro: MacroParams) -> tuple[RealEstateParams, PortfolioParams, BenchmarkParams, int, bool, MonteCarloParams]:
    """Build sidebar inputs and return parameter objects."""
    st.sidebar.title("⚙️ Parâmetros")
    st.sidebar.caption(f"Cenário macroeconômico: {TODAY_LABEL} — {macro.source_label}")

    capital = st.sidebar.number_input(
        "Capital inicial (R$)",
        min_value=10_000.0, max_value=10_000_000.0, value=230_000.0, step=10_000.0,
        format="%.0f",
    )
    horizon = st.sidebar.slider("Horizonte (anos)", 1, 30, 10)
    reinvest = st.sidebar.checkbox("Reinvestir rendimentos", value=True)

    st.sidebar.markdown("---")
    st.sidebar.subheader("🏠 Imóvel")
    re_params = RealEstateParams(property_value=capital)
    re_params.monthly_rent = st.sidebar.number_input(
        "Aluguel mensal (R$)", 500.0, 50_000.0, 1_500.0, 100.0, format="%.0f")
    re_params.annual_appreciation = st.sidebar.slider(
        "Valorização anual (%)", 0.0, 15.0, 5.5, 0.5) / 100
    re_params.iptu_rate = st.sidebar.slider(
        "IPTU (% do valor)", 0.0, 3.0, 1.0, 0.1) / 100
    re_params.vacancy_months_per_year = st.sidebar.slider(
        "Vacância (meses/ano)", 0.0, 4.0, 1.0, 0.5)
    re_params.management_fee_pct = st.sidebar.slider(
        "Adm. imobiliária (%)", 0.0, 15.0, 10.0, 0.5) / 100
    re_params.income_tax_bracket = st.sidebar.slider(
        "IR sobre aluguel (%)", 0.0, 27.5, 7.5, 0.5) / 100

    financing_enabled = st.sidebar.checkbox(
        "Financiar imóvel",
        value=False,
        help="Quando ligado, simula entrada + parcelas. Capital inicial cobre a entrada; sobra entra na carteira interna.",
    )
    if financing_enabled:
        with st.sidebar.expander("Detalhes do financiamento", expanded=True):
            entry_pct = st.slider("Entrada (% do imóvel)", 10, 80, 20, 5) / 100
            term_years = st.slider("Prazo (anos)", 5, 35, 30, 1)
            annual_rate = st.slider("Taxa anual (%)", 6.0, 18.0, 11.5, 0.25) / 100
            system = st.radio("Sistema", ["SAC", "Price"], horizontal=True)
        re_params.financing = FinancingParams(
            term_years=term_years,
            annual_rate=annual_rate,
            entry_pct=entry_pct,
            system=system,
        )

    st.sidebar.markdown("---")
    st.sidebar.subheader("💰 Aporte mensal (Carteira)")
    monthly_contribution = st.sidebar.number_input(
        "Valor mensal (R$, em valor de hoje)",
        min_value=0.0, max_value=100_000.0, value=0.0, step=100.0,
        format="%.0f",
        help="Valor adicionado mensalmente à carteira. Imóvel não recebe aportes.",
    )
    indexed = st.sidebar.checkbox(
        "Indexar pelo IPCA",
        value=True,
        help="Quando ligado, o aporte cresce ano a ano pela inflação esperada (mantém poder de compra).",
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("📈 Carteira Diversificada")
    pf_params = PortfolioParams(
        capital=capital,
        monthly_contribution=monthly_contribution,
        contribution_inflation_indexed=indexed,
    )
    with st.sidebar.expander("Ajustar pesos e yields", expanded=False):
        for asset in pf_params.assets:
            st.markdown(f"**{asset.name}**")
            asset.weight = st.slider(
                f"Peso — {asset.name}", 0.0, 1.0, asset.weight, 0.05,
                key=f"w_{asset.name}")
            asset.expected_yield = st.slider(
                f"Yield (%) — {asset.name}", 0.0, 20.0,
                asset.expected_yield * 100, 0.5,
                key=f"y_{asset.name}") / 100
        pf_params.normalize_weights()

    st.sidebar.markdown("---")
    st.sidebar.subheader("📊 Benchmark RF")
    bench_params = BenchmarkParams(capital=capital)
    bench_params.selic_rate = st.sidebar.slider(
        "Taxa Selic (%)", 5.0, 20.0, macro.selic * 100, 0.25) / 100

    st.sidebar.markdown("---")
    st.sidebar.subheader("🎲 Análise estocástica")
    target_patrimony = st.sidebar.number_input(
        "Meta de patrimônio (R$)",
        min_value=0.0, max_value=100_000_000.0, value=0.0, step=50_000.0,
        format="%.0f",
        help="Patrimônio-alvo no horizonte. Mostra prob. de bater. 0 desativa.",
    )
    with st.sidebar.expander("Volatilidades (σ anual)", expanded=False):
        for asset in pf_params.assets:
            asset.volatility = st.slider(
                f"σ — {asset.name} (%)", 0.0, 50.0, asset.volatility * 100, 1.0,
                key=f"vol_{asset.name}",
            ) / 100
        re_params.appreciation_volatility = st.slider(
            "σ — Valorização imóvel (%)", 0.0, 30.0,
            re_params.appreciation_volatility * 100, 1.0,
        ) / 100
    mc_params = MonteCarloParams(target_patrimony=target_patrimony)

    st.sidebar.markdown("---")
    if st.sidebar.button("🔄 Recarregar dados macro", use_container_width=True):
        get_macro_params.clear()
        st.rerun()

    return re_params, pf_params, bench_params, horizon, reinvest, mc_params


# ---------- Page sections ----------

def _run_simulations(
    re_params: RealEstateParams,
    pf_params: PortfolioParams,
    bench_params: BenchmarkParams,
    horizon: int,
    reinvest: bool,
    ipca: float,
):
    """Run all three simulations consistently for both overview and export."""
    re_kwargs = {}
    if re_params.financing is not None:
        re_kwargs["capital_initial"] = re_params.property_value
        re_kwargs["internal_portfolio_rate"] = pf_params.total_return()
    return (
        simulate_real_estate(re_params, horizon, reinvest, **re_kwargs),
        simulate_portfolio(pf_params, horizon, reinvest, ipca=ipca),
        simulate_benchmark(bench_params, horizon),
    )


def _run_monte_carlo(
    re_params: RealEstateParams,
    pf_params: PortfolioParams,
    horizon: int,
    mc_params: MonteCarloParams,
    ipca: float,
) -> tuple[MonteCarloResult, MonteCarloResult]:
    """Run Monte Carlo for both Carteira and Imóvel scenarios."""
    pf_mc = simulate_portfolio_mc(pf_params, horizon, mc_params, ipca=ipca)
    re_kwargs = {}
    if re_params.financing is not None:
        re_kwargs["capital_initial"] = re_params.property_value
        re_kwargs["portfolio_for_internal"] = pf_params
    re_mc = simulate_real_estate_mc(re_params, horizon, mc_params, **re_kwargs)
    return re_mc, pf_mc


def render_overview(re_params: RealEstateParams,
                    pf_params: PortfolioParams,
                    bench_params: BenchmarkParams,
                    horizon: int,
                    reinvest: bool,
                    macro: MacroParams,
                    re_result: SimulationResult,
                    pf_result: SimulationResult,
                    bench_result: SimulationResult) -> None:
    """Top-level KPI dashboard and patrimony evolution."""
    final_re = re_result.patrimony[-1]
    final_pf = pf_result.patrimony[-1]
    final_bench = bench_result.patrimony[-1]
    capital = re_params.property_value

    st.markdown("## 📌 Visão Geral")

    cols = st.columns(4)
    with cols[0]:
        st.metric(
            "Yield líquido — Imóvel",
            f"{re_params.net_yield():.2%}",
            f"{(re_params.net_yield() - pf_params.blended_yield()):+.2%} vs. Carteira",
            delta_color="inverse",
        )
    with cols[1]:
        st.metric(
            "DY blended — Carteira",
            f"{pf_params.blended_yield():.2%}",
            f"{(pf_params.blended_yield() - re_params.net_yield()):+.2%} vs. Imóvel",
        )
    with cols[2]:
        diff = (final_pf - final_re) / capital * 100
        st.metric(
            f"Patrimônio Imóvel ({horizon}a)",
            f"R$ {final_re:,.0f}".replace(",", "."),
            f"{re_params.total_return():.2%} a.a.",
        )
    with cols[3]:
        st.metric(
            f"Patrimônio Carteira ({horizon}a)",
            f"R$ {final_pf:,.0f}".replace(",", "."),
            f"{pf_params.total_return():.2%} a.a.",
        )

    st.markdown("### Evolução comparativa do patrimônio")
    st.plotly_chart(
        patrimony_evolution_chart([re_result, pf_result, bench_result]),
        use_container_width=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Renda mensal gerada")
        st.plotly_chart(annual_income_chart([re_result, pf_result]),
                        use_container_width=True)
    with col2:
        st.markdown("### Mapa risco × retorno")
        st.plotly_chart(risk_return_scatter(), use_container_width=True)

    # Summary table
    st.markdown("### Tabela consolidada")
    df = pd.DataFrame([
        {
            "Cenário": re_result.label,
            "Yield líquido": f"{re_params.net_yield():.2%}",
            "Retorno total a.a.": f"{re_params.total_return():.2%}",
            f"Patrimônio Ano {horizon}": f"R$ {final_re:,.0f}".replace(",", "."),
            f"Renda mensal Ano {horizon}": f"R$ {re_result.annual_income[-1] / 12:,.0f}".replace(",", "."),
        },
        {
            "Cenário": "Carteira Diversificada",
            "Yield líquido": f"{pf_params.blended_yield():.2%}",
            "Retorno total a.a.": f"{pf_params.total_return():.2%}",
            f"Patrimônio Ano {horizon}": f"R$ {final_pf:,.0f}".replace(",", "."),
            f"Renda mensal Ano {horizon}": f"R$ {pf_result.annual_income[-1] / 12:,.0f}".replace(",", "."),
        },
        {
            "Cenário": "Tesouro Selic líquido",
            "Yield líquido": f"{bench_params.net_yield():.2%}",
            "Retorno total a.a.": f"{bench_params.net_yield():.2%}",
            f"Patrimônio Ano {horizon}": f"R$ {final_bench:,.0f}".replace(",", "."),
            f"Renda mensal Ano {horizon}": "—",
        },
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_real_estate(re_params: RealEstateParams, re_result: SimulationResult) -> None:
    """Detailed real estate breakdown."""
    st.markdown("## 🏠 Análise do Imóvel")

    cols = st.columns(4)
    cols[0].metric("Yield Bruto", f"{re_params.gross_yield():.2%}")
    cols[1].metric("Yield Líquido", f"{re_params.net_yield():.2%}",
                   f"{re_params.net_yield() - re_params.gross_yield():.2%}")
    cols[2].metric("Receita Líquida Anual",
                   f"R$ {re_params.net_annual_income():,.0f}".replace(",", "."))
    cols[3].metric("Custo Total Anual",
                   f"R$ {re_params.total_costs():,.0f}".replace(",", "."),
                   f"{re_params.total_costs() / re_params.gross_annual_rent():.1%} da receita",
                   delta_color="inverse")

    if re_params.financing is not None and re_result.debt_balance is not None:
        fin = re_params.financing
        entry = re_params.property_value * fin.entry_pct
        loan = re_params.property_value - entry
        schedule = build_schedule(fin, loan)
        first_payment = float(schedule.payments[0])
        total_interest = float(schedule.interest.sum())

        st.markdown("### 💼 Financiamento")
        cols = st.columns(4)
        cols[0].metric("Entrada", f"R$ {entry:,.0f}".replace(",", "."))
        cols[1].metric(
            "Parcela inicial", f"R$ {first_payment:,.0f}".replace(",", "."),
            help=f"Primeira parcela ({fin.system}). Em SAC, parcelas decrescem; em Price, ficam constantes.",
        )
        cols[2].metric("Total de juros", f"R$ {total_interest:,.0f}".replace(",", "."))
        cols[3].metric("Prazo", f"{fin.term_years} anos")

        if re_result.internal_portfolio is not None and re_result.internal_portfolio.min() < 0:
            negative_year = int(re_result.years[re_result.internal_portfolio < 0][0])
            st.warning(
                f"⚠️ Cenário com fluxo negativo: a carteira interna do Imóvel fica deficitária "
                f"a partir do ano {negative_year}. Em vida real, isso exigiria injeção de capital "
                f"externo. Considere aumentar a entrada, o prazo, ou o aluguel-alvo."
            )

        st.plotly_chart(
            debt_evolution_chart(re_result.years, re_result.debt_balance),
            use_container_width=True,
        )

    st.markdown("### Decomposição de receita e custos")
    st.plotly_chart(income_vs_costs_waterfall(re_params), use_container_width=True)

    col1, col2 = st.columns(2)
    with col1:
        costs = {
            "IPTU": re_params.annual_iptu(),
            "Vacância": re_params.vacancy_loss(),
            "Manutenção": re_params.maintenance_annual,
            "Adm. Imobiliária": re_params.management_fee(),
            "Seguro": re_params.insurance_annual,
            "IR sobre Aluguel": re_params.income_tax_amount(),
        }
        st.plotly_chart(cost_breakdown_chart(costs), use_container_width=True)

    with col2:
        st.markdown("### Custos não-recorrentes (compra)")
        acquisition_cost = re_params.property_value * re_params.acquisition_cost_pct
        df_acq = pd.DataFrame([
            {"Item": "ITBI + cartório + escritura",
             "Valor": f"R$ {acquisition_cost:,.0f}".replace(",", ".")},
            {"Item": "Reformas e preparação", "Valor": "R$ 5.000 a R$ 15.000"},
            {"Item": "Mobília básica (opcional)", "Valor": "R$ 8.000 a R$ 20.000"},
            {"Item": "Seguro fiança (caução depósito)",
             "Valor": f"R$ {re_params.monthly_rent * 3:,.0f}".replace(",", ".")},
        ])
        st.dataframe(df_acq, use_container_width=True, hide_index=True)

        st.markdown("### Riscos críticos")
        st.markdown("""
        - **Concentração**: 1 ativo = 100% do capital
        - **Iliquidez**: 3-12 meses para venda
        - **Inadimplência**: 1-2 meses comuns mesmo com fiança
        - **Vacância prolongada**: paralisa receita
        - **Risco regulatório**: lei do inquilinato favorece locatário
        - **Depreciação**: reformas estruturais a cada 7-10 anos
        """)


def render_portfolio(pf_params: PortfolioParams, macro: MacroParams) -> None:
    """Portfolio allocation analysis."""
    st.markdown("## 📈 Análise da Carteira Diversificada")

    cols = st.columns(4)
    cols[0].metric("DY blended", f"{pf_params.blended_yield():.2%}")
    cols[1].metric("Ganho de capital esperado",
                   f"{pf_params.blended_capital_gain():.2%}")
    cols[2].metric("Retorno total a.a.",
                   f"{pf_params.total_return():.2%}")
    cols[3].metric("Renda anual estimada",
                   f"R$ {pf_params.annual_income():,.0f}".replace(",", "."))

    col1, col2 = st.columns([1.2, 1])
    with col1:
        st.plotly_chart(portfolio_donut_chart(pf_params), use_container_width=True)
    with col2:
        st.markdown("### Detalhamento por classe")
        df = pd.DataFrame([
            {
                "Classe": a.name,
                "Peso": f"{a.weight:.1%}",
                "Valor": f"R$ {pf_params.capital * a.weight:,.0f}".replace(",", "."),
                "Yield Esp.": f"{a.expected_yield:.2%}",
                "Tributação": f"{a.tax_rate:.1%}",
            }
            for a in pf_params.assets
        ])
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### Yields comparados")
    yields = {
        "Imóvel bruto": 0.0783,
        "Imóvel líquido": 0.0415,
        "FIIs (IFIX)": 0.118,
        "Ações BR": 0.09,
        "Tesouro Selic líq.": macro.selic * (1 - 0.175),
        "Carteira blended": pf_params.blended_yield(),
    }
    st.plotly_chart(
        yield_comparison_bars(yields, {"Selic": macro.selic, "IPCA": macro.ipca}),
        use_container_width=True,
    )


def render_sensitivity(re_params: RealEstateParams, horizon: int) -> None:
    """Sensitivity analysis for real estate scenario."""
    st.markdown("## 🎯 Análise de Sensibilidade")
    st.caption("Variação de parâmetros-chave do cenário imóvel e impacto no patrimônio final.")

    deltas = {
        "monthly_rent": (re_params.monthly_rent * 0.8, re_params.monthly_rent * 1.2),
        "annual_appreciation": (re_params.annual_appreciation - 0.03,
                                re_params.annual_appreciation + 0.03),
        "vacancy_months_per_year": (0.0, 3.0),
        "management_fee_pct": (0.0, 0.15),
        "iptu_rate": (0.005, 0.020),
        "income_tax_bracket": (0.0, 0.275),
    }

    df = sensitivity_real_estate(re_params, horizon, deltas)

    # Translate parameter names
    name_map = {
        "monthly_rent": "Aluguel mensal (±20%)",
        "annual_appreciation": "Valorização (±3pp)",
        "vacancy_months_per_year": "Vacância (0-3 meses)",
        "management_fee_pct": "Adm. imobiliária (0-15%)",
        "iptu_rate": "IPTU (0,5-2%)",
        "income_tax_bracket": "Faixa IR (0-27,5%)",
    }
    df["Parâmetro"] = df["Parâmetro"].map(name_map)

    base_value = float(df["Cenário Base"].iloc[0])
    st.plotly_chart(sensitivity_tornado_chart(df, base_value),
                    use_container_width=True)

    st.markdown("### Tabela detalhada")
    df_display = df.copy()
    for col in ["Cenário Pessimista", "Cenário Base", "Cenário Otimista"]:
        df_display[col] = df_display[col].apply(
            lambda v: f"R$ {v:,.0f}".replace(",", "."))
    st.dataframe(df_display, use_container_width=True, hide_index=True)


def render_taxes(re_params: RealEstateParams, pf_params: PortfolioParams) -> None:
    """Tax comparison view."""
    st.markdown("## 💸 Comparativo Tributário")

    df = annual_tax_comparison(re_params, pf_params)
    st.plotly_chart(tax_comparison_chart(df), use_container_width=True)

    st.markdown("### Detalhamento")
    df_display = df.copy()
    for col in ["Receita Bruta", "Imposto Anual", "Receita Líquida"]:
        df_display[col] = df_display[col].apply(
            lambda v: f"R$ {v:,.0f}".replace(",", "."))
    df_display["Carga Tributária Efetiva"] = df_display["Carga Tributária Efetiva"].apply(
        lambda v: f"{v:.2%}")
    st.dataframe(df_display, use_container_width=True, hide_index=True)

    st.markdown("""
    <div class='info-card'>
    <b>📌 Notas tributárias (cenário 2026):</b><br>
    • <b>FIIs</b>: rendimentos mensais permanecem isentos para PF<br>
    • <b>Ações BR (dividendos)</b>: isentos até R$ 50k/mês ou R$ 600k/ano por empresa<br>
    • <b>Ações US (dividendos)</b>: 30% retido na fonte (com tratado: pode reduzir)<br>
    • <b>Aluguel</b>: tabela progressiva via carnê-leão (até 27,5%)<br>
    • <b>Tesouro</b>: tabela regressiva (15% a 22,5%)<br>
    </div>
    """, unsafe_allow_html=True)


def render_export(re_params: RealEstateParams,
                  pf_params: PortfolioParams,
                  bench_params: BenchmarkParams,
                  horizon: int,
                  reinvest: bool,
                  macro: MacroParams,
                  re_result: SimulationResult,
                  pf_result: SimulationResult,
                  bench_result: SimulationResult) -> None:
    """Export simulation results to CSV."""
    st.markdown("## 📥 Exportar Dados")

    df = build_comparison_dataframe([re_result, pf_result, bench_result])

    st.dataframe(df, use_container_width=True, hide_index=True)

    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, sep=";", decimal=",", encoding="utf-8-sig")
    st.download_button(
        label="⬇️ Baixar simulação (CSV)",
        data=csv_buffer.getvalue(),
        file_name=f"simulacao_imovel_vs_carteira_{horizon}anos.csv",
        mime="text/csv",
    )


# ---------- Main ----------

def main() -> None:
    macro = get_macro_params()

    st.title("📊 Imóvel vs. Carteira Diversificada")
    st.caption(
        f"**Análise Buy & Hold** — Macro: Selic {macro.selic:.2%} | "
        f"IPCA esp. {macro.ipca:.2%} | CDI {macro.cdi:.2%} | "
        f"USD/BRL {macro.usd_brl:.2f} ({macro.source_label})"
    )

    if macro.is_stale:
        st.warning(
            "⚠️ Indicadores macro indisponíveis ao vivo. Usando referências de "
            f"{TODAY_LABEL}. Tente recarregar em alguns minutos."
        )

    re_params, pf_params, bench_params, horizon, reinvest, mc_params = render_sidebar(macro)

    if re_params.financing is not None:
        entry_required = re_params.property_value * re_params.financing.entry_pct
        # NOTE: capital_initial currently equals property_value because the sidebar
        # uses a single "Capital inicial" input for both. With entry_pct bounded
        # to [0.10, 0.80] by the slider, the guard below is structurally unreachable
        # today. It will become meaningful when capital and property value are
        # decoupled (deferred to Phase 3+).
        capital_initial = re_params.property_value
        if capital_initial < entry_required:
            st.error(
                f"Capital insuficiente: a entrada exige R$ {entry_required:,.0f}".replace(",", ".")
                + f", mas o capital inicial é R$ {capital_initial:,.0f}.".replace(",", ".")
                + " Aumente o capital ou reduza a % de entrada."
            )
            st.stop()

    tabs = st.tabs([
        "📌 Visão Geral",
        "🏠 Imóvel",
        "📈 Carteira",
        "🎯 Sensibilidade",
        "💸 Tributação",
        "📥 Exportar",
    ])

    re_result, pf_result, bench_result = _run_simulations(
        re_params, pf_params, bench_params, horizon, reinvest, macro.ipca,
    )
    re_mc, pf_mc = _run_monte_carlo(re_params, pf_params, horizon, mc_params, macro.ipca)

    with tabs[0]:
        render_overview(re_params, pf_params, bench_params, horizon, reinvest, macro,
                        re_result, pf_result, bench_result)
    with tabs[1]:
        render_real_estate(re_params, re_result)
    with tabs[2]:
        render_portfolio(pf_params, macro)
    with tabs[3]:
        render_sensitivity(re_params, horizon)
    with tabs[4]:
        render_taxes(re_params, pf_params)
    with tabs[5]:
        render_export(re_params, pf_params, bench_params, horizon, reinvest, macro,
                      re_result, pf_result, bench_result)

    st.markdown("---")
    st.caption(
        "💡 Dashboard técnico para análise de cenário. "
        "Não constitui recomendação formal de investimento. "
        f"Premissas baseadas em {macro.source_label}."
    )


if __name__ == "__main__":
    main()
