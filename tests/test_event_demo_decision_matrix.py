"""ER-B expected-vs-actual decision matrix tests."""

from __future__ import annotations

from riskon.demo.models import DashboardView


def test_decision_matrix_has_all_nine_cells(event_demo_dashboard: DashboardView) -> None:
    matrix = event_demo_dashboard.decision_matrix
    assert matrix.labels == ["ANSWER", "CLARIFY", "ABSTAIN"]
    assert len(matrix.cells) == 9
    assert sum(cell.count for cell in matrix.cells) == 5


def test_decision_matrix_keeps_case_ids_in_diagonal_cells(
    event_demo_dashboard: DashboardView,
) -> None:
    nonzero = {
        (cell.expected, cell.actual): cell.case_ids
        for cell in event_demo_dashboard.decision_matrix.cells
        if cell.count
    }
    assert nonzero == {
        ("ANSWER", "ANSWER"): ["M4D-041", "M4D-044", "M4D-045"],
        ("CLARIFY", "CLARIFY"): ["M4D-042"],
        ("ABSTAIN", "ABSTAIN"): ["M4D-043"],
    }
