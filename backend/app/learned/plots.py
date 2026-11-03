"""Accuracy-cost and accuracy-latency comparison plots for the held-out test (week of Nov 5).

    uv run --project backend python -m app.learned.plots

Reads the committed report and writes PNG and SVG figures to ``docs/figures``. Each plot has one
axis pair (no dual axes): accuracy against total cost, and accuracy against median latency, as
small multiples for all prompts and for each task group. The learned router and the baselines
use categorical slots 1 and 2 of a colorblind-validated palette, plus different marker shapes,
and every point is labeled directly; the report's tables hold the exact values.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator, MultipleLocator  # noqa: E402
from matplotlib.transforms import Bbox  # noqa: E402

from app.config import REPOSITORY_ROOT  # noqa: E402
from app.domain.models import LearnedRouterReport, LearnedStrategyOutcome  # noqa: E402

REPORT_PATH = REPOSITORY_ROOT / "data" / "learned" / "cp3-full-router-comparison.json"
FIGURE_DIR = REPOSITORY_ROOT / "docs" / "figures"
# Light-mode chart tokens from the dataviz reference palette (validated, slots 1 and 2).
SURFACE, INK, INK_SECONDARY, MUTED = "#fcfcfb", "#0b0b0b", "#52514e", "#898781"
GRID, AXIS = "#e1e0d9", "#c3c2b7"
LEARNED_COLOR, BASELINE_COLOR = "#2a78d6", "#eb6834"
LABELS = {
    "fixed_cheapest": "Always cheapest",
    "fixed_strongest": "Always strongest",
    "rule_balanced": "CP2 rule router",
    "learned:quality": "Learned · quality",
    "learned:cost": "Learned · cost",
    "learned:latency": "Learned · faster",
    "learned:balanced": "Learned · balanced",
}
PANELS = [
    (None, "All prompts"),
    ("math", "GSM8K (math)"),
    ("qa", "MMLU-Pro (QA)"),
    ("code", "HumanEval+ and MBPP+ (code)"),
]
# Label offsets in points, tried in order; the first clear one wins, else the least overlap.
OFFSETS = [(9, 5, "left"), (9, -13, "left"), (-9, 5, "right"), (-9, -13, "right"),
           (0, 11, "center"), (0, -19, "center"), (9, 16, "left"), (9, -24, "left"),
           (-9, 16, "right"), (-9, -24, "right")]


@dataclass(frozen=True)
class Point:
    label: str
    learned: bool
    accuracy: float
    cost: float
    latency_s: float


def _points(strategies: list[LearnedStrategyOutcome], task: str | None) -> list[Point]:
    """One marker per series at each spot; strategies at the same spot share one label."""
    merged: dict[tuple[float, float, float], list[str]] = {}
    for strategy in strategies:
        if strategy.strategy_id not in LABELS:
            continue
        outcome = strategy if task is None else strategy.by_task[task]
        key = (
            round(outcome.accuracy * 100, 3),
            round(outcome.total_cost_usd, 6),
            round((outcome.median_latency_ms or 0.0) / 1000, 2),
        )
        merged.setdefault(key, []).append(strategy.strategy_id)
    points = []
    for key, ids in merged.items():
        baselines = [LABELS[item] for item in ids if not item.startswith("learned:")]
        learned = [LABELS[item].split(" · ")[1] for item in ids if item.startswith("learned:")]
        label = " = ".join(baselines + (["Learned · " + ", ".join(learned)] if learned else []))
        for is_learned in sorted({item.startswith("learned:") for item in ids}):
            # Only the last marker at a spot carries the label, so it is drawn once.
            points.append(Point("", is_learned, key[0], key[1], key[2]))
        points[-1] = Point(label, points[-1].learned, key[0], key[1], key[2])
    return points


def _place_labels(ax: Axes, points: list[Point], x_of: Callable[[Point], float]) -> None:
    figure = ax.figure
    renderer = figure.canvas.get_renderer()  # type: ignore[attr-defined]
    frame = ax.get_window_extent(renderer)
    taken: list[Bbox] = []
    centers = [tuple(ax.transData.transform((x_of(point), point.accuracy))) for point in points]
    for x, y in centers:
        taken.append(Bbox.from_extents(x - 7, y - 7, x + 7, y + 7))

    def overlap(box: Bbox, own: tuple[float, float]) -> float:
        inside = frame.contains(box.x0, box.y0) and frame.contains(box.x1, box.y1)
        shared = 0.0
        for other in taken:
            both = Bbox.intersection(box, other)
            shared += both.width * both.height if both is not None else 0.0
        # No other point may sit closer to the label than the label's own point.
        def distance(center: tuple[float, ...]) -> float:
            dx = max(box.x0 - center[0], 0.0, center[0] - box.x1)
            dy = max(box.y0 - center[1], 0.0, center[1] - box.y1)
            return float(dx * dx + dy * dy)

        mine = distance(own)
        misleading = any(distance(center) < mine for center in centers if center != own)
        return shared + (0.0 if inside else 1e9) + (5e4 if misleading else 0.0)

    for point in sorted(points, key=lambda item: -item.accuracy):
        if not point.label:
            continue
        best: tuple[float, Bbox, tuple[int, int, str]] | None = None
        for offset in OFFSETS:
            dx, dy, align = offset
            text = ax.annotate(
                point.label, (x_of(point), point.accuracy), xytext=(dx, dy),
                textcoords="offset points", ha=align, fontsize=8.5, color=INK_SECONDARY,
            )
            box = text.get_window_extent(renderer).expanded(1.04, 1.15)
            own = tuple(ax.transData.transform((x_of(point), point.accuracy)))
            cost = overlap(box, (float(own[0]), float(own[1])))
            if best is None or cost < best[0]:
                best = (cost, box, offset)
            text.remove()
            if cost == 0:
                break
        assert best is not None
        _, box, (dx, dy, align) = best
        ax.annotate(point.label, (x_of(point), point.accuracy), xytext=(dx, dy),
                    textcoords="offset points", ha=align, fontsize=8.5, color=INK_SECONDARY)
        taken.append(box)


def _panel(
    ax: Axes,
    points: list[Point],
    x_of: Callable[[Point], float],
    title: str,
    x_label: str,
    x_unit: tuple[str, str],
) -> None:
    ax.set_facecolor(SURFACE)
    # Baseline squares are drawn larger and underneath, so a shared spot still shows both.
    for learned, color, marker, size in (
        (False, BASELINE_COLOR, "s", 110), (True, LEARNED_COLOR, "o", 70)
    ):
        group = [point for point in points if point.learned == learned]
        ax.scatter(
            [x_of(point) for point in group], [point.accuracy for point in group],
            s=size, marker=marker, color=color, edgecolors=SURFACE, linewidths=2,
            zorder=3 + learned, clip_on=False,
            label="Learned router" if learned else "Baselines",
        )
    xs = [x_of(point) for point in points]
    ys = [point.accuracy for point in points]
    span = max(xs) or 1.0
    ax.set_xlim(-0.05 * span, span * 1.42)  # room for labels right of the rightmost points
    low, high = min(ys), max(ys)
    ax.set_ylim(max(0.0, (low // 5) * 5 - 2), min(100.0, high + 3.5))
    ax.yaxis.set_major_locator(MultipleLocator(5))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))
    ax.xaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
    ticks = [tick for tick in ax.get_xticks() if tick >= 0]
    step = f"{ticks[1] - ticks[0]:g}" if len(ticks) > 1 else "1"
    prefix, suffix = x_unit
    # As many decimals as the tick step needs (2.5 s, $0.025); whole cents at least for cost.
    decimals = max(len(step.partition(".")[2]), 2 if prefix == "$" else 0)
    ax.xaxis.set_major_formatter(FuncFormatter(
        lambda value, _: "" if value < 0 else f"{prefix}{value:.{decimals}f}{suffix}"
    ))
    ax.grid(True, color=GRID, linewidth=0.8, linestyle="-")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(AXIS)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(colors=MUTED, labelsize=8.5, length=0)
    ax.set_title(title, loc="left", fontsize=10.5, color=INK, fontweight="semibold", pad=8)
    ax.set_xlabel(x_label, fontsize=9, color=INK_SECONDARY)
    ax.set_ylabel("Correct answers", fontsize=9, color=INK_SECONDARY)
    ax.figure.canvas.draw()
    _place_labels(ax, points, x_of)


def figure(
    report: LearnedRouterReport,
    title: str,
    x_of: Callable[[Point], float],
    x_label: str,
    x_unit: tuple[str, str],
    out: Path,
) -> list[Path]:
    fig, axes = plt.subplots(2, 2, figsize=(12, 8.2), facecolor=SURFACE)
    held = report.heldout
    for ax, (task, name) in zip(axes.flat, PANELS, strict=True):
        points = _points(held.strategies, task)
        count = (
            held.prompts if task is None
            else next(iter(held.strategies)).by_task[task].prompts
        )
        _panel(ax, points, x_of, f"{name} · {count} prompts", x_label, x_unit)
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", frameon=False, fontsize=9.5, ncol=2,
               labelcolor=INK_SECONDARY, bbox_to_anchor=(0.985, 0.985))
    fig.suptitle(title, x=0.015, y=0.975, ha="left", fontsize=13, color=INK,
                 fontweight="semibold")
    fig.text(0.015, 0.935, (
        f"Held-out test split, read once. Router {held.artifact_id}, trained on "
        f"{' + '.join(held.trained_on)}; outcomes replayed from the saved matrix."
    ), fontsize=9, color=MUTED)
    fig.tight_layout(rect=(0, 0, 1, 0.92), h_pad=2.2, w_pad=2.5)
    for ax in axes.flat:  # tight_layout moved the axes, so place the labels again
        for text in list(ax.texts):
            text.remove()
    fig.canvas.draw()
    for ax, (task, _) in zip(axes.flat, PANELS, strict=True):
        _place_labels(ax, _points(held.strategies, task), x_of)
    written = []
    for suffix in (".png", ".svg"):
        path = out.with_suffix(suffix)
        fig.savefig(path, dpi=160, facecolor=SURFACE,
                    metadata={"Date": None} if suffix == ".svg" else {"Software": None})
        written.append(path)
    plt.close(fig)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    args = parser.parse_args()
    report = LearnedRouterReport.model_validate_json(args.report.read_text(encoding="utf-8"))
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["svg.hashsalt"] = "cp3-heldout"  # fixed element IDs, so reruns are identical
    written = figure(
        report, "Accuracy against cost on held-out prompts", lambda point: point.cost,
        "Total paid cost (USD)", ("$", ""), FIGURE_DIR / "cp3-heldout-accuracy-cost",
    )
    written += figure(
        report, "Accuracy against response time on held-out prompts",
        lambda point: point.latency_s, "Median latency (seconds)", ("", " s"),
        FIGURE_DIR / "cp3-heldout-accuracy-latency",
    )
    for path in written:
        print(f"wrote {path.relative_to(REPOSITORY_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
