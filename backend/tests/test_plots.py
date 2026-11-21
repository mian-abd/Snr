import xml.etree.ElementTree as ElementTree
from pathlib import Path

import matplotlib.pyplot as plt
import pytest

from app.domain.models import FinalEvaluationReport, RobustnessReport
from app.learned import plots

STEMS = {
    "cp3-heldout-accuracy-cost",
    "cp3-heldout-accuracy-latency",
    "final-robustness",
    "final-robustness-cost",
    "final-priority-sweep",
}


def _fresh_robustness() -> RobustnessReport:
    report = FinalEvaluationReport.model_validate_json(
        plots.FINAL_REPORT_PATH.read_text(encoding="utf-8")
    )
    return next(item for item in report.robustness if item.evaluation_id == "final")


def test_every_figure_renders_from_the_committed_reports(tmp_path: Path) -> None:
    for folder, theme in (("light", plots.LIGHT), ("slides", plots.SLIDE)):
        written = plots.write_all(tmp_path / folder, theme)
        assert {path.name for path in written} == {
            f"{stem}{suffix}" for stem in STEMS for suffix in (".png", ".svg")
        }
        for path in written:
            assert path.parent == tmp_path / folder
            if path.suffix == ".png":
                assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
            else:
                ElementTree.parse(path)  # well-formed SVG
        svg = (tmp_path / folder / "final-robustness.svg").read_text(encoding="utf-8")
        for title in ("Observed drift (Nov 12-13)", "Gemini 4 Argon fails 30% of calls",
                      "Router told about the change", "Same router, old estimates"):
            assert title in svg  # scenario titles and the legend are real text
        sweep = (tmp_path / folder / "final-priority-sweep.svg").read_text(encoding="utf-8")
        assert "w = 0.1" in sweep and "$0" in sweep


def test_dumbbells_pair_the_told_router_with_its_old_estimates() -> None:
    fresh = _fresh_robustness()
    rows = plots._dumbbells(fresh, "latency", lambda item: float(item.correct))
    observed = [row for row in rows if row.observed]
    assert len(rows) == len(fresh.scenarios) and len(observed) == 1
    # Told that Mercury 3 was retired, the fastest setting routes around it; with its old
    # estimates it keeps sending prompts to the retired model.
    assert (observed[0].told, observed[0].old, observed[0].reference) == (276.0, 83.0, 284.0)
    assert plots._balanced_matches_fastest(fresh)


def test_free_cost_sits_left_of_the_cheapest_paid_value() -> None:
    fig, ax = plt.subplots()
    position = plots._cost_axis(ax, [0.0, 0.0034, 1.16], plots.LIGHT)
    assert position(0.0) == pytest.approx(1e-4) and position(0.0034) == 0.0034
    labels = [plots._dollars(tick) for tick in (1e-3, 0.01, 0.1, 1.0)]
    assert labels == ["$0.001", "$0.01", "$0.1", "$1"]
    plt.close(fig)
