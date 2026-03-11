"""Simple propane deasphalting (PDA) unit simulator.

This script models:
- DAO yield
- DAO viscosity
- Asphaltene carryover (ppm in DAO)
- Color risk category

It uses simplified empirical refinery-style correlations (not EOS-based models).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable



@dataclass
class FeedComposition:
    """Feed composition in mass fractions."""

    dao_oil: float
    resins: float
    asphaltenes: float

    def normalize(self) -> "FeedComposition":
        total = self.dao_oil + self.resins + self.asphaltenes
        if total <= 0:
            raise ValueError("Feed composition total must be positive.")
        return FeedComposition(
            dao_oil=self.dao_oil / total,
            resins=self.resins / total,
            asphaltenes=self.asphaltenes / total,
        )


@dataclass
class PDAModelParameters:
    """Model constants for simplified PDA correlations."""

    ymax: float = 0.85
    k: float = 0.8
    a: float = 0.7
    c_entrain: float = 0.03


@dataclass
class PDAResult:
    solvent_oil_ratio: float
    dao_yield: float
    dao_viscosity_cst_100c: float
    asphaltene_ppm_in_dao: float
    color_category: str


class PDASimulator:
    def __init__(
        self,
        feed: FeedComposition,
        mw_dao: float = 450.0,
        mw_resins: float = 700.0,
        params: PDAModelParameters | None = None,
    ) -> None:
        self.feed = feed.normalize()
        self.mw_dao = mw_dao
        self.mw_resins = mw_resins
        self.params = params or PDAModelParameters()

    def dao_yield(self, so_ratio: float) -> float:
        # DAO_yield = Ymax*(1-exp(-k*(SO_ratio)))
        return self.params.ymax * (1 - math.exp(-self.params.k * so_ratio))

    def asphaltene_precipitation(self, so_ratio: float) -> float:
        # A_precip = A_feed*(1-exp(-a*(SO_ratio)))
        return self.feed.asphaltenes * (1 - math.exp(-self.params.a * so_ratio))

    def asphaltene_ppm_in_dao(self, so_ratio: float, dao_yield: float | None = None) -> float:
        if dao_yield is None:
            dao_yield = self.dao_yield(so_ratio)

        a_precip = self.asphaltene_precipitation(so_ratio)
        # A_DAO = A_precip * C_entrain
        a_dao_mass_fraction_feed_basis = a_precip * self.params.c_entrain

        if dao_yield <= 0:
            return float("inf")

        # Convert to DAO-basis mass fraction and then to ppm
        a_dao_mass_fraction_dao_basis = a_dao_mass_fraction_feed_basis / dao_yield
        return a_dao_mass_fraction_dao_basis * 1_000_000

    def dao_viscosity_100c(self, so_ratio: float) -> float:
        dao_y = self.dao_yield(so_ratio)
        if dao_y <= 0:
            return float("inf")

        # approximate resin recovery with DAO; less severe extraction keeps more resins in DAO
        resin_recovery = max(0.0, min(1.0, 1 - math.exp(-0.6 * so_ratio)))

        dao_component_in_dao = self.feed.dao_oil * dao_y
        resin_component_in_dao = self.feed.resins * resin_recovery
        total_heavy_liquid = dao_component_in_dao + resin_component_in_dao

        if total_heavy_liquid <= 0:
            return float("inf")

        mw_avg = (
            dao_component_in_dao * self.mw_dao + resin_component_in_dao * self.mw_resins
        ) / total_heavy_liquid

        # log(viscosity) = 0.5 + 0.003*MW_avg
        log_mu = 0.5 + 0.003 * mw_avg
        return math.exp(log_mu)

    @staticmethod
    def color_risk(asphaltene_ppm: float) -> str:
        if asphaltene_ppm < 100:
            return "acceptable"
        if asphaltene_ppm <= 300:
            return "dark"
        return "DMA risk"

    def simulate(self, so_ratio: float) -> PDAResult:
        dao_y = self.dao_yield(so_ratio)
        asph_ppm = self.asphaltene_ppm_in_dao(so_ratio, dao_yield=dao_y)
        viscosity = self.dao_viscosity_100c(so_ratio)
        return PDAResult(
            solvent_oil_ratio=so_ratio,
            dao_yield=dao_y,
            dao_viscosity_cst_100c=viscosity,
            asphaltene_ppm_in_dao=asph_ppm,
            color_category=self.color_risk(asph_ppm),
        )


def sensitivity_analysis(simulator: PDASimulator, so_ratios: Iterable[float]) -> list[PDAResult]:
    return [simulator.simulate(r) for r in so_ratios]


def print_single_case(result: PDAResult) -> None:
    print("PDA SIMULATION RESULT")
    print(f"Solvent/Oil ratio  : {result.solvent_oil_ratio:.2f}")
    print(f"DAO yield          : {result.dao_yield * 100:.2f} wt% of feed")
    print(f"DAO viscosity @100C: {result.dao_viscosity_cst_100c:.2f} cSt")
    print(f"Asphaltene in DAO  : {result.asphaltene_ppm_in_dao:.1f} ppm")
    print(f"Color category     : {result.color_category}")


def plot_sensitivity(results: list[PDAResult], outfile: str = "pda_sensitivity.png") -> None:
    """Create requested sensitivity plots if matplotlib is available.

    If matplotlib is unavailable, save tabular data to CSV for later plotting.
    """
    ratios = [r.solvent_oil_ratio for r in results]
    dao_yield = [r.dao_yield * 100 for r in results]
    asph_ppm = [r.asphaltene_ppm_in_dao for r in results]
    viscosity = [r.dao_viscosity_cst_100c for r in results]

    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        csv_out = "pda_sensitivity.csv"
        with open(csv_out, "w", encoding="utf-8") as f:
            f.write("so_ratio,dao_yield_wt_percent,asphaltene_ppm,viscosity_cst_100c\n")
            for r in results:
                f.write(
                    f"{r.solvent_oil_ratio},{r.dao_yield * 100},{r.asphaltene_ppm_in_dao},{r.dao_viscosity_cst_100c}\n"
                )
        print(
            "matplotlib not available: skipped figure generation. "
            f"Sensitivity data written to {csv_out}."
        )
        return

    fig, axes = plt.subplots(3, 1, figsize=(8, 12), sharex=True)

    axes[0].plot(ratios, dao_yield, marker="o")
    axes[0].set_ylabel("DAO yield (wt% feed)")
    axes[0].set_title("DAO yield vs solvent/oil ratio")
    axes[0].grid(True, alpha=0.3)

    axes[1].plot(ratios, asph_ppm, marker="o", color="tab:red")
    axes[1].set_ylabel("Asphaltene in DAO (ppm)")
    axes[1].set_title("Asphaltene carryover vs solvent/oil ratio")
    axes[1].grid(True, alpha=0.3)

    axes[2].plot(ratios, viscosity, marker="o", color="tab:green")
    axes[2].set_xlabel("Solvent/Oil ratio")
    axes[2].set_ylabel("DAO viscosity @100C (cSt)")
    axes[2].set_title("DAO viscosity vs solvent/oil ratio")
    axes[2].grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(outfile, dpi=150)
    print(f"Sensitivity plot saved to: {outfile}")


def main() -> None:
    # Example feed composition input (mass fractions)
    feed = FeedComposition(dao_oil=0.72, resins=0.18, asphaltenes=0.10)

    simulator = PDASimulator(feed=feed)

    # single case report
    base_ratio = 5.0
    result = simulator.simulate(base_ratio)
    print_single_case(result)

    # sensitivity analysis
    ratios = [x / 2 for x in range(2, 21)]  # 1.0 to 10.0
    results = sensitivity_analysis(simulator, ratios)
    plot_sensitivity(results)


if __name__ == "__main__":
    main()
