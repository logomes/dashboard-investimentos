"""Default scenario parameters and macro constants.

Single source of truth for all financial assumptions used throughout the
dashboard. Updating values here propagates to every screen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Final, Literal


# ---------- Macro context (Apr/2026) ----------

SELIC_RATE: Final[float] = 0.1475
IPCA_EXPECTED: Final[float] = 0.048
CDI_RATE: Final[float] = 0.1465
USD_BRL: Final[float] = 5.30
TODAY_LABEL: Final[str] = "Abril/2026"


@dataclass(slots=True, frozen=True)
class MacroParams:
    """Macro indicators consumed by the app. May come from BCB live or fallback."""
    selic: float
    ipca: float
    cdi: float
    usd_brl: float
    is_stale: bool                       # True when fallback values are used
    source_label: str                    # "BCB SGS (live)" or "Fallback (Abr/2026)"


MACRO_FALLBACK: Final[MacroParams] = MacroParams(
    selic=SELIC_RATE,
    ipca=IPCA_EXPECTED,
    cdi=CDI_RATE,
    usd_brl=USD_BRL,
    is_stale=True,
    source_label=f"Fallback ({TODAY_LABEL})",
)


# ---------- Financing ----------

@dataclass(slots=True, frozen=True)
class FinancingParams:
    """Real-estate financing terms (loan principal, rate, system, insurance)."""
    term_years: int = 30
    annual_rate: float = 0.115
    entry_pct: float = 0.20
    system: Literal["SAC", "Price"] = "SAC"
    monthly_insurance_rate: float = 0.0005

    @property
    def monthly_rate(self) -> float:
        return (1 + self.annual_rate) ** (1 / 12) - 1


# ---------- Real Estate defaults (R$ 230k in São Paulo) ----------

@dataclass(slots=True)
class RealEstateParams:
    property_value: float = 230_000.0
    monthly_rent: float = 1_500.0
    annual_appreciation: float = 0.055        # IPCA + 1%
    iptu_rate: float = 0.010                  # 1% of property value
    vacancy_months_per_year: float = 1.0
    management_fee_pct: float = 0.10          # 10% of rent to admin
    maintenance_annual: float = 900.0
    insurance_annual: float = 600.0
    income_tax_bracket: float = 0.075         # carnê-leão typical bracket
    acquisition_cost_pct: float = 0.05        # ITBI + cartório
    appreciation_volatility: float = 0.10     # σ anual da valorização
    financing: FinancingParams | None = None

    def gross_annual_rent(self) -> float:
        return self.monthly_rent * 12

    def annual_iptu(self) -> float:
        return self.property_value * self.iptu_rate

    def vacancy_loss(self) -> float:
        return self.monthly_rent * self.vacancy_months_per_year

    def management_fee(self) -> float:
        return self.gross_annual_rent() * self.management_fee_pct

    def income_tax_amount(self) -> float:
        # Tax applies on rent received (after vacancy)
        taxable = self.gross_annual_rent() - self.vacancy_loss()
        return taxable * self.income_tax_bracket

    def total_costs(self) -> float:
        return (
            self.annual_iptu()
            + self.vacancy_loss()
            + self.maintenance_annual
            + self.management_fee()
            + self.insurance_annual
            + self.income_tax_amount()
        )

    def net_annual_income(self) -> float:
        return self.gross_annual_rent() - self.total_costs()

    def gross_yield(self) -> float:
        return self.gross_annual_rent() / self.property_value

    def net_yield(self) -> float:
        return self.net_annual_income() / self.property_value

    def total_return(self) -> float:
        """Total nominal return = net yield + appreciation."""
        return self.net_yield() + self.annual_appreciation


# ---------- Portfolio defaults ----------

@dataclass(slots=True)
class AssetClass:
    name: str
    weight: float
    expected_yield: float
    capital_gain: float = 0.0
    tax_rate: float = 0.0
    note: str = ""
    volatility: float = 0.15   # σ anual do retorno total (yield + capital gain)

    @property
    def gross_return(self) -> float:
        return self.expected_yield + self.capital_gain

    @property
    def net_return(self) -> float:
        return self.expected_yield * (1 - self.tax_rate) + self.capital_gain


@dataclass(slots=True)
class PortfolioParams:
    capital: float = 230_000.0
    assets: list[AssetClass] = field(default_factory=lambda: [
        AssetClass("FIIs de Papel",         0.25, 0.130, 0.00, 0.00,
                   "HGCR11, KNCR11, RBRR11 — isento PF",
                   volatility=0.14),
        AssetClass("FIIs de Tijolo",        0.25, 0.090, 0.02, 0.00,
                   "HGLG11, XPML11, KNRI11 — isento PF",
                   volatility=0.16),
        AssetClass("Ações BR Dividendos",   0.20, 0.090, 0.03, 0.00,
                   "ITSA4, BBAS3, TAEE11, EGIE3",
                   volatility=0.27),
        AssetClass("Dividend Aristocrats US", 0.15, 0.040, 0.06, 0.30,
                   "JNJ, ABBV, O, MSFT (via Avenue)",
                   volatility=0.18),
        AssetClass("Tesouro IPCA+ / LCI",   0.15, 0.115, 0.00, 0.10,
                   "NTN-B 2035, LCI 100% CDI",
                   volatility=0.05),
    ])
    monthly_contribution: float = 0.0           # R$/month, in today's value
    contribution_inflation_indexed: bool = True

    def normalize_weights(self) -> None:
        """Force weights to sum to 1.0."""
        total = sum(a.weight for a in self.assets)
        if total <= 0:
            return
        for a in self.assets:
            a.weight /= total

    def blended_yield(self) -> float:
        return sum(a.weight * a.expected_yield * (1 - a.tax_rate)
                   for a in self.assets)

    def blended_capital_gain(self) -> float:
        return sum(a.weight * a.capital_gain for a in self.assets)

    def total_return(self) -> float:
        return self.blended_yield() + self.blended_capital_gain()

    def annual_income(self) -> float:
        return self.capital * self.blended_yield()


# ---------- Monte Carlo ----------

@dataclass(slots=True, frozen=True)
class MonteCarloParams:
    """Parameters for Monte Carlo stochastic simulation."""
    n_trajectories: int = 10_000
    seed: int = 42
    target_patrimony: float = 0.0   # 0 desativa cálculo de prob de bater meta


# ---------- Reference benchmark (Tesouro Selic líquido) ----------

@dataclass(slots=True)
class BenchmarkParams:
    capital: float = 230_000.0
    selic_rate: float = SELIC_RATE
    tax_rate: float = 0.175  # IR 17.5% (>2 anos)

    def net_yield(self) -> float:
        return self.selic_rate * (1 - self.tax_rate)


# ---------- Renda Fixa (fixed-income positions) ----------

IndexerKind = Literal["prefixado", "cdi", "selic", "ipca"]


@dataclass(slots=True)
class FixedIncomePosition:
    """One fixed-income holding (CDB, LCI, Tesouro, debênture, etc.)."""
    name: str
    initial_amount: float
    purchase_date: date
    indexer: IndexerKind
    rate: float
    maturity_date: date | None = None
    is_tax_exempt: bool = False
    color: str = "#3498DB"

    def effective_annual_rate(self, macro: "MacroParams") -> float:
        """Convert the position's indexer + rate into a nominal annual rate."""
        match self.indexer:
            case "prefixado":
                return self.rate
            case "cdi":
                return macro.cdi * self.rate
            case "selic":
                return macro.selic + self.rate
            case "ipca":
                return (1 + macro.ipca) * (1 + self.rate) - 1


# ---------- Visual palette ----------

PALETTE: Final[dict[str, str]] = {
    "imovel": "#C0392B",
    "carteira": "#27AE60",
    "fii_papel": "#2980B9",
    "fii_tijolo": "#5DADE2",
    "acoes_br": "#8E44AD",
    "acoes_us": "#16A085",
    "rf": "#F39C12",
    "neutral": "#34495E",
    "background": "#F8F9FA",
    "grid": "#ECF0F1",
}
