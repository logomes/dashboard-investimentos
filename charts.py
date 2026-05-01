"""Interactive Plotly chart builders.

All charts use a consistent visual identity defined in `config.PALETTE`.
Functions return Plotly figures that can be directly rendered with
`st.plotly_chart`.
"""

from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from config import PALETTE, PortfolioParams
from models import SimulationResult


_LAYOUT_DEFAULTS = dict(
    template="plotly_white",
    font=dict(family="Inter, system-ui, sans-serif", size=13, color="#2C3E50"),
    title_font=dict(size=18, color="#1F3A5F"),
    margin=dict(l=60, r=40, t=70, b=50),
    plot_bgcolor="white",
    paper_bgcolor="white",
    hoverlabel=dict(font_size=12, font_family="Inter"),
)

# Apply on top of _LAYOUT_DEFAULTS for charts that show a horizontal legend
# below the plot — extends bottom margin so axis title and legend don't collide.
_BOTTOM_LEGEND = dict(
    margin=dict(l=60, r=40, t=70, b=110),
    legend=dict(
        orientation="h", yanchor="top", y=-0.32,
        xanchor="center", x=0.5,
        bgcolor="rgba(255,255,255,0.9)",
    ),
)


def _format_currency(value: float) -> str:
    return f"R$ {value:,.0f}".replace(",", ".")


def patrimony_evolution_chart(results: Iterable[SimulationResult]) -> go.Figure:
    """Line chart with patrimony evolution over time."""
    fig = go.Figure()
    for r in results:
        fig.add_trace(go.Scatter(
            x=r.years,
            y=r.patrimony,
            mode="lines+markers",
            name=r.label,
            line=dict(color=r.color, width=3),
            marker=dict(size=7),
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Ano %{x}<br>"
                "Patrimônio: R$ %{y:,.0f}<extra></extra>"
            ),
        ))

    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        **_BOTTOM_LEGEND,
        title="Evolução do Patrimônio ao Longo do Tempo",
        xaxis_title="Anos",
        yaxis_title="Patrimônio (R$)",
        hovermode="x unified",
        height=460,
    )
    fig.update_yaxes(tickformat=",.0f", tickprefix="R$ ")
    fig.update_xaxes(dtick=1)
    return fig


def annual_income_chart(results: Iterable[SimulationResult]) -> go.Figure:
    """Annual income generation over time."""
    fig = go.Figure()
    for r in results:
        fig.add_trace(go.Scatter(
            x=r.years,
            y=r.annual_income / 12,  # monthly
            mode="lines+markers",
            name=r.label,
            line=dict(color=r.color, width=3),
            marker=dict(size=7),
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Ano %{x}<br>"
                "Renda mensal: R$ %{y:,.0f}<extra></extra>"
            ),
        ))

    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        **_BOTTOM_LEGEND,
        title="Renda Mensal Gerada (R$)",
        xaxis_title="Anos",
        yaxis_title="Renda Mensal (R$)",
        hovermode="x unified",
        height=420,
    )
    fig.update_yaxes(tickformat=",.0f", tickprefix="R$ ")
    fig.update_xaxes(dtick=1)
    return fig


def cost_breakdown_chart(costs: dict[str, float]) -> go.Figure:
    """Horizontal bar chart of real estate costs."""
    sorted_items = sorted(costs.items(), key=lambda x: x[1], reverse=False)
    labels = [k for k, _ in sorted_items]
    values = [v for _, v in sorted_items]
    total = sum(values)
    pct = [v / total * 100 for v in values]

    fig = go.Figure(go.Bar(
        x=values,
        y=labels,
        orientation="h",
        marker=dict(
            color=values,
            colorscale=[[0, "#7B241C"], [1, "#E74C3C"]],
            line=dict(color="white", width=1.5),
        ),
        text=[f"R$ {v:,.0f} ({p:.1f}%)".replace(",", ".") for v, p in zip(values, pct)],
        textposition="outside",
        hovertemplate="<b>%{y}</b><br>R$ %{x:,.0f}<extra></extra>",
    ))

    fig.update_layout(
        **{**_LAYOUT_DEFAULTS, "showlegend": False},
        title=f"Custos Anuais do Imóvel — Total: R$ {total:,.0f}".replace(",", "."),
        xaxis_title="Custo Anual (R$)",
        height=380,
    )
    fig.update_xaxes(tickformat=",.0f", tickprefix="R$ ", range=[0, max(values) * 1.4])
    return fig


def portfolio_donut_chart(portfolio: PortfolioParams) -> go.Figure:
    """Donut chart showing portfolio allocation."""
    colors = [
        PALETTE["fii_papel"], PALETTE["fii_tijolo"],
        PALETTE["acoes_br"], PALETTE["acoes_us"], PALETTE["rf"],
    ]

    labels = [a.name for a in portfolio.assets]
    weights = [a.weight * 100 for a in portfolio.assets]
    yields_text = [
        f"DY {a.expected_yield:.1%} | Peso {a.weight:.0%}"
        for a in portfolio.assets
    ]

    fig = go.Figure(go.Pie(
        labels=labels,
        values=weights,
        hole=0.55,
        marker=dict(colors=colors[:len(labels)], line=dict(color="white", width=2)),
        textinfo="label+percent",
        textposition="outside",
        customdata=yields_text,
        hovertemplate="<b>%{label}</b><br>%{customdata}<br>Valor: R$ %{value:.0f}k<extra></extra>",
    ))

    blended = portfolio.blended_yield()
    fig.update_layout(
        **{**_LAYOUT_DEFAULTS, "showlegend": False},
        title="Alocação da Carteira",
        annotations=[dict(
            text=f"<b>R$ {portfolio.capital/1000:,.0f}k</b><br>"
                 f"<span style='color:#27AE60'>DY blended {blended:.1%}</span>".replace(",", "."),
            x=0.5, y=0.5, showarrow=False, font=dict(size=15),
        )],
        height=440,
    )
    return fig


def sensitivity_tornado_chart(df: pd.DataFrame, base_value: float) -> go.Figure:
    """Tornado chart for sensitivity analysis."""
    df = df.copy()
    df["Δ Pessimista"] = df["Cenário Pessimista"] - base_value
    df["Δ Otimista"] = df["Cenário Otimista"] - base_value
    df["Spread"] = df["Δ Otimista"].abs() + df["Δ Pessimista"].abs()
    df = df.sort_values("Spread", ascending=True)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=df["Parâmetro"],
        x=df["Δ Pessimista"],
        orientation="h",
        name="Pessimista",
        marker=dict(color=PALETTE["imovel"]),
        hovertemplate="<b>%{y}</b><br>Δ: R$ %{x:,.0f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        y=df["Parâmetro"],
        x=df["Δ Otimista"],
        orientation="h",
        name="Otimista",
        marker=dict(color=PALETTE["carteira"]),
        hovertemplate="<b>%{y}</b><br>Δ: R$ %{x:,.0f}<extra></extra>",
    ))
    fig.add_vline(x=0, line=dict(color="#34495E", width=2))

    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        **_BOTTOM_LEGEND,
        title="Análise de Sensibilidade — Impacto no Patrimônio Final",
        xaxis_title="Variação do Patrimônio (R$)",
        barmode="overlay",
        height=420,
    )
    fig.update_xaxes(tickformat=",.0f", tickprefix="R$ ")
    return fig


def risk_return_scatter() -> go.Figure:
    """Risk vs return scatter map of available asset classes."""
    assets = [
        ("Tesouro Selic",          0.5,  12.0, PALETTE["rf"],         700),
        ("Tesouro IPCA+",          6.0,  11.5, "#E67E22",             700),
        ("Imóvel residencial",     8.0,   9.65, PALETTE["imovel"],   900),
        ("FIIs (IFIX)",           12.0,  12.0, PALETTE["fii_papel"], 900),
        ("Ações BR Dividendos",   22.0,  13.0, PALETTE["acoes_br"], 800),
        ("Dividend Aristocrats",  14.0,  11.0, PALETTE["acoes_us"], 800),
        ("Carteira Diversificada", 9.0, 10.5, PALETTE["carteira"], 1100),
    ]

    fig = go.Figure()
    for name, vol, ret, color, size in assets:
        fig.add_trace(go.Scatter(
            x=[vol], y=[ret], mode="markers+text",
            marker=dict(size=size / 30, color=color, opacity=0.8,
                        line=dict(color="white", width=2)),
            text=[name], textposition="top center",
            textfont=dict(size=11, color="#2C3E50"),
            hovertemplate=f"<b>{name}</b><br>Volatilidade: {vol:.1f}%<br>Retorno: {ret:.1f}%<extra></extra>",
            showlegend=False,
        ))

    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        title="Mapa Risco × Retorno (a.a.)",
        xaxis_title="Volatilidade Anualizada (%)",
        yaxis_title="Retorno Esperado Nominal (%)",
        height=460,
    )
    fig.update_xaxes(ticksuffix="%", range=[-1, 26])
    fig.update_yaxes(ticksuffix="%", range=[8, 14.5])
    return fig


def yield_comparison_bars(yields: dict[str, float], reference_lines: dict[str, float]) -> go.Figure:
    """Bar chart comparing yields across asset classes."""
    labels = list(yields.keys())
    values = [v * 100 for v in yields.values()]

    colors = [
        PALETTE["imovel"], PALETTE["imovel"], PALETTE["fii_papel"],
        PALETTE["acoes_br"], PALETTE["rf"], PALETTE["carteira"],
    ][:len(labels)]

    fig = go.Figure(go.Bar(
        x=labels, y=values, marker=dict(color=colors, line=dict(color="white", width=2)),
        text=[f"{v:.2f}%" for v in values], textposition="outside",
        hovertemplate="<b>%{x}</b><br>Yield: %{y:.2f}%<extra></extra>",
    ))

    for ref_name, ref_value in reference_lines.items():
        fig.add_hline(
            y=ref_value * 100,
            line=dict(color="#7F8C8D", width=1.5, dash="dot"),
            annotation_text=f"{ref_name}: {ref_value:.2%}",
            annotation_position="right",
        )

    fig.update_layout(
        **{**_LAYOUT_DEFAULTS, "showlegend": False},
        title="Yields Anuais Comparados (Cenário Atual)",
        yaxis_title="Yield Anual (%)",
        height=420,
    )
    fig.update_yaxes(ticksuffix="%", range=[0, max(values) * 1.25])
    return fig


def income_vs_costs_waterfall(real_estate_params) -> go.Figure:
    """Waterfall chart showing rent → net income for real estate."""
    gross = real_estate_params.gross_annual_rent()
    iptu = real_estate_params.annual_iptu()
    vacancy = real_estate_params.vacancy_loss()
    maint = real_estate_params.maintenance_annual
    mgmt = real_estate_params.management_fee()
    insurance = real_estate_params.insurance_annual
    tax = real_estate_params.income_tax_amount()
    net = real_estate_params.net_annual_income()

    fig = go.Figure(go.Waterfall(
        orientation="v",
        measure=["absolute", "relative", "relative", "relative",
                 "relative", "relative", "relative", "total"],
        x=["Receita Bruta", "IPTU", "Vacância", "Manutenção",
           "Adm. Imobiliária", "Seguro", "IR", "Receita Líquida"],
        y=[gross, -iptu, -vacancy, -maint, -mgmt, -insurance, -tax, net],
        text=[f"R$ {v:,.0f}".replace(",", ".") for v in
              [gross, -iptu, -vacancy, -maint, -mgmt, -insurance, -tax, net]],
        textposition="outside",
        connector=dict(line=dict(color="#95A5A6", width=1)),
        increasing=dict(marker=dict(color=PALETTE["carteira"])),
        decreasing=dict(marker=dict(color=PALETTE["imovel"])),
        totals=dict(marker=dict(color=PALETTE["neutral"])),
        hovertemplate="<b>%{x}</b><br>R$ %{y:,.0f}<extra></extra>",
    ))

    fig.update_layout(
        **{**_LAYOUT_DEFAULTS, "showlegend": False},
        title="Decomposição da Receita Anual do Imóvel",
        yaxis_title="Valor Anual (R$)",
        height=440,
    )
    fig.update_yaxes(tickformat=",.0f", tickprefix="R$ ")
    return fig


def tax_comparison_chart(df: pd.DataFrame) -> go.Figure:
    """Bar chart comparing tax burden between scenarios."""
    fig = make_subplots(
        rows=1, cols=2,
        subplot_titles=("Imposto Anual (R$)", "Carga Tributária Efetiva (%)"),
        horizontal_spacing=0.15,
    )

    fig.add_trace(
        go.Bar(
            x=df["Cenário"], y=df["Imposto Anual"],
            marker=dict(color=[PALETTE["imovel"], PALETTE["carteira"]]),
            text=[f"R$ {v:,.0f}".replace(",", ".") for v in df["Imposto Anual"]],
            textposition="outside", showlegend=False,
            hovertemplate="<b>%{x}</b><br>Imposto: R$ %{y:,.0f}<extra></extra>",
        ),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(
            x=df["Cenário"], y=df["Carga Tributária Efetiva"] * 100,
            marker=dict(color=[PALETTE["imovel"], PALETTE["carteira"]]),
            text=[f"{v*100:.1f}%" for v in df["Carga Tributária Efetiva"]],
            textposition="outside", showlegend=False,
            hovertemplate="<b>%{x}</b><br>Carga: %{y:.2f}%<extra></extra>",
        ),
        row=1, col=2,
    )

    fig.update_layout(
        **{**_LAYOUT_DEFAULTS, "showlegend": False},
        title="Comparativo Tributário",
        height=400,
    )
    fig.update_yaxes(tickformat=",.0f", tickprefix="R$ ", row=1, col=1)
    fig.update_yaxes(ticksuffix="%", row=1, col=2)
    return fig


def debt_evolution_chart(
    years: np.ndarray,
    debt_balance: np.ndarray,
) -> go.Figure:
    """Area chart of outstanding loan balance over time."""
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=years,
        y=debt_balance,
        mode="lines",
        fill="tozeroy",
        line=dict(color=PALETTE["imovel"], width=2),
        name="Saldo devedor",
        hovertemplate="Ano %{x}<br>Saldo: R$ %{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        **{**_LAYOUT_DEFAULTS, "showlegend": False},
        title="Saldo Devedor ao Longo do Tempo",
        xaxis_title="Ano",
        yaxis_title="Saldo (R$)",
        height=360,
    )
    fig.update_yaxes(tickformat=",.0f", tickprefix="R$ ")
    fig.update_xaxes(dtick=1)
    return fig


def patrimony_band_chart(
    mc_results: list,
    deterministic_results: list | None = None,
) -> go.Figure:
    """Banda p10–p90 sombreada + linha p50 por cenário.

    When `deterministic_results` is provided, draws solid dashed lines on top
    using the same color per scenario (paired by list order).
    """
    fig = go.Figure()

    for mc in mc_results:
        years = np.arange(len(mc.percentiles["p10"]))
        # Upper band edge (p90) — invisible marker (used as anchor for fill)
        fig.add_trace(go.Scatter(
            x=years, y=mc.percentiles["p90"],
            mode="lines",
            line=dict(width=0),
            showlegend=False,
            hoverinfo="skip",
            name=f"{mc.label} p90",
        ))
        # Lower band edge (p10) with fill back up to p90
        fig.add_trace(go.Scatter(
            x=years, y=mc.percentiles["p10"],
            mode="lines",
            line=dict(width=0),
            fill="tonexty",
            fillcolor=_band_fill(mc.color),
            showlegend=False,
            hoverinfo="skip",
            name=f"{mc.label} p10",
        ))
        # Median line
        fig.add_trace(go.Scatter(
            x=years, y=mc.percentiles["p50"],
            mode="lines",
            line=dict(color=mc.color, width=2),
            name=f"{mc.label} p50",
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Ano %{x}<br>"
                "Patrimônio: R$ %{y:,.0f}<extra></extra>"
            ),
        ))

    if deterministic_results is not None:
        for det in deterministic_results:
            fig.add_trace(go.Scatter(
                x=det.years, y=det.patrimony,
                mode="lines",
                line=dict(color=det.color, width=2, dash="dash"),
                name=f"{det.label} (det)",
                hovertemplate=(
                    "<b>%{fullData.name}</b><br>"
                    "Ano %{x}<br>"
                    "Patrimônio: R$ %{y:,.0f}<extra></extra>"
                ),
            ))

    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        **_BOTTOM_LEGEND,
        title="Evolução do patrimônio — banda p10–p90 (Monte Carlo)",
        xaxis_title="Ano",
        yaxis_title="Patrimônio (R$)",
        hovermode="x unified",
        height=420,
    )
    fig.update_yaxes(tickformat=",.0f", tickprefix="R$ ")
    fig.update_xaxes(dtick=1)
    return fig


def _band_fill(hex_color: str) -> str:
    """Convert #RRGGBB to rgba(R,G,B,0.18) for soft band fill."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r},{g},{b},0.18)"


def distribution_histogram_chart(mc_result, target: float = 0.0) -> go.Figure:
    """Histogram of the final-year patrimony distribution. Target line shown if > 0."""
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=mc_result.final_distribution,
        nbinsx=40,
        marker=dict(color=mc_result.color, opacity=0.7),
        name=mc_result.label,
        hovertemplate=(
            f"<b>{mc_result.label}</b><br>"
            "Patrimônio: R$ %{x:,.0f}<br>"
            "Frequência: %{y}<extra></extra>"
        ),
    ))
    if target > 0:
        fig.add_vline(
            x=target, line=dict(color="#2C3E50", width=2, dash="dash"),
            annotation_text=f"Meta: R$ {target:,.0f}".replace(",", "."),
            annotation_position="top right",
        )
    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        title=f"Distribuição final — {mc_result.label}",
        xaxis_title="Patrimônio final (R$)",
        yaxis_title="Frequência",
        height=320,
        showlegend=False,
    )
    fig.update_xaxes(tickformat=",.0f", tickprefix="R$ ")
    return fig


def fixed_income_evolution_chart(portfolio) -> go.Figure:
    """Line chart with net evolution per fixed-income position over time."""
    fig = go.Figure()
    for proj in portfolio.projections:
        fig.add_trace(go.Scatter(
            x=proj.years,
            y=proj.net_values,
            mode="lines+markers",
            name=proj.position.name,
            line=dict(color=proj.position.color, width=3),
            marker=dict(size=6),
            hovertemplate=(
                "<b>%{fullData.name}</b><br>"
                "Ano %{x}<br>"
                "Líquido: R$ %{y:,.0f}<extra></extra>"
            ),
        ))

    fig.update_layout(
        **_LAYOUT_DEFAULTS,
        title="Evolução líquida por posição",
        xaxis_title="Anos",
        yaxis_title="Valor líquido (R$)",
        hovermode="x unified",
        height=440,
    )
    fig.update_yaxes(tickformat=",.0f", tickprefix="R$ ")
    fig.update_xaxes(dtick=1)
    return fig
