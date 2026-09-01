"""In-process regression gate for the frozen M0--M4D evaluators."""

from __future__ import annotations

from typing import Any

from riskon.governance.models import RegressionGateResult


class RegressionGate:
    """Run the existing evaluator stack without subprocesses or recursion."""

    def __init__(self, milestone5b_config: Any) -> None:
        self.config = milestone5b_config

    def run(self) -> RegressionGateResult:
        """Execute M4D once; its document contains all upstream regressions."""

        from riskon.m4d_evaluation import M4DEvaluator

        try:
            document = M4DEvaluator(self.config.base).run()
        except Exception:
            return RegressionGateResult(
                expected=45,
                matched=0,
                suites={},
                network_enabled=True,
            )

        suites = {
            "M4D": _contract(document.m4d_contract),
            "M4A": _contract(document.m4a_regression),
            "M4B": _contract(document.m4b_regression),
            "M4C": _contract(document.m4c_regression),
            "M0_M3": _contract(document.m0_m3_regression),
        }
        expected = sum(item["expected"] for item in suites.values())
        matched = sum(item["matched"] for item in suites.values())
        return RegressionGateResult(
            expected=expected,
            matched=matched,
            suites=suites,
            network_enabled=bool(document.network_enabled),
        )


def _contract(value: dict[str, Any]) -> dict[str, int]:
    """Keep only the safe aggregate fields from an evaluator document."""

    return {"expected": int(value.get("expected", 0)), "matched": int(value.get("matched", 0))}
