"""Comparison, robustness, and priority-sweep plots for the held-out evaluations (Nov 5, Nov 26).

    uv run --project backend python -m app.learned.plots
    uv run --project backend python -m app.learned.plots --slides OUT_DIR   # dark, for a deck

Reads the committed reports and writes PNG and SVG figures to ``docs/figures``. Each plot has one
axis pair (no dual axes).

- ``cp3-heldout-accuracy-{cost,latency}``: accuracy against total cost and against median
  latency on the Checkpoint 3 test split, as small multiples for all prompts and for each task
  group. Every point is labeled directly; the report's tables hold the exact values.
- ``final-robustness`` and ``final-robustness-cost``: one row per robustness scenario on the
  fresh prompts and one panel per priority, as dumbbells joining the router told about the
  change and the same router keeping its old estimates; the always-strongest baseline is a faint
  reference tick and the change that really happened sits on a shaded band. Right answers, then
  billed cost on a log scale with free ($0) at the left.
- ``final-priority-sweep``: accuracy against billed cost as the cost weight rises, and against
  median time as the latency weight rises, each point labeled with its weight where it fits.
- ``scoring-fix-robustness``: the four scenarios the scoring fix targets, as dumbbells for the
  frozen and the fixed scoring, told and with old estimates: right answers, then median time or
  billed cost.

Series use categorical slots 1 and 2 of a colorblind-validated palette; where two share a
panel they also differ in marker shape and have a legend. ``--slides`` writes the all-prompts
comparison panel alone and the other figures without their headings, in the same slots' dark
steps and larger type.
"""

from __future__ import annotations

import argparse
import math
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.artist import Artist  # noqa: E402
from matplotlib.axes import Axes  # noqa: E402
from matplotlib.figure import Figure  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from matplotlib.path import Path as MarkerPath  # noqa: E402
from matplotlib.ticker import (  # noqa: E402
    FixedLocator,
    FuncFormatter,
    MaxNLocator,
    MultipleLocator,
    NullLocator,
)
from matplotlib.transforms import Bbox  # noqa: E402

from app.config import REPOSITORY_ROOT  # noqa: E402
from app.domain.models import (  # noqa: E402
    FinalEvaluationReport,
    LearnedRouterReport,
    LearnedStrategyOutcome,
    PrioritySweepPoint,
    RobustnessReport,
    ScenarioStrategy,
)
from app.domain.scoring_fix import ScoringFixEvaluation, ScoringFixReport  # noqa: E402

REPORT_PATH = REPOSITORY_ROOT / "data" / "learned" / "cp3-full-router-comparison.json"
FINAL_REPORT_PATH = REPOSITORY_ROOT / "data" / "learned" / "final-evaluation.json"
SCORING_FIX_PATH = REPOSITORY_ROOT / "data" / "learned" / "scoring-fix-study.json"
FIGURE_DIR = REPOSITORY_ROOT / "docs" / "figures"


@dataclass(frozen=True)
class Theme:
    surface: str
    ink: str
    ink_secondary: str
    muted: str
    grid: str
    axis: str
    learned: str
    baseline: str
    scale: float = 1.0  # type, marker, and label-offset scale
    band: str = "#f0efec"  # a neutral one step off the surface, behind a highlighted row


# Light-mode chart tokens from the dataviz reference palette (validated, slots 1 and 2).
LIGHT = Theme("#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7",
              "#2a78d6", "#eb6834")
# The same slots' dark steps (validated on dark surfaces), on the deck's card color.
SLIDE = Theme("#111316", "#f0efec", "#c3c2b7", "#898781", "#2c2c2a", "#383835",
              "#3987e5", "#d95926", scale=1.75, band="#1f2125")
LABELS = {
    "fixed_cheapest": "Always cheapest",
    "fixed_strongest": "Always strongest",
    "rule_balanced": "Rule-based router",
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


def _place_labels(
    ax: Axes,
    points: list[Point],
    x_of: Callable[[Point], float],
    theme: Theme,
    skip_crowded: bool = False,
    obstacles: list[Bbox] | None = None,
) -> None:
    """Label each point at the first clear offset. With ``skip_crowded``, a label that has no
    clear spot is left out instead of placed where it overlaps least. ``obstacles`` are more
    display-space boxes to keep labels off (unlabeled markers, a line)."""
    figure = ax.figure
    renderer = figure.canvas.get_renderer()  # type: ignore[attr-defined]
    frame = ax.get_window_extent(renderer)
    taken: list[Bbox] = []
    centers = [tuple(ax.transData.transform((x_of(point), point.accuracy))) for point in points]
    reach = 7 * theme.scale
    for x, y in centers:
        taken.append(Bbox.from_extents(x - reach, y - reach, x + reach, y + reach))
    taken.extend(obstacles or [])

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
        best: tuple[float, Bbox, tuple[float, float, str]] | None = None
        for base_dx, base_dy, align in OFFSETS:
            offset = (base_dx * theme.scale, base_dy * theme.scale, align)
            dx, dy, _ = offset
            text = ax.annotate(
                point.label, (x_of(point), point.accuracy), xytext=(dx, dy),
                textcoords="offset points", ha=align, fontsize=8.5 * theme.scale,
                color=theme.ink_secondary,
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
        if skip_crowded and best[0] > 0:
            continue
        _, box, (dx, dy, align) = best
        ax.annotate(point.label, (x_of(point), point.accuracy), xytext=(dx, dy),
                    textcoords="offset points", ha=align, fontsize=8.5 * theme.scale,
                    color=theme.ink_secondary)
        taken.append(box)


def _panel(
    ax: Axes,
    points: list[Point],
    x_of: Callable[[Point], float],
    title: str,
    x_label: str,
    x_unit: tuple[str, str],
    theme: Theme,
) -> None:
    size = theme.scale
    ax.set_facecolor(theme.surface)
    # Baseline squares are drawn larger and underneath, so a shared spot still shows both.
    for learned, color, marker, area in (
        (False, theme.baseline, "s", 110), (True, theme.learned, "o", 70)
    ):
        group = [point for point in points if point.learned == learned]
        ax.scatter(
            [x_of(point) for point in group], [point.accuracy for point in group],
            s=area * size * size, marker=marker, color=color, edgecolors=theme.surface,
            linewidths=2 * size, zorder=3 + learned, clip_on=False,
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
    ax.grid(True, color=theme.grid, linewidth=0.8 * size, linestyle="-")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(theme.axis)
        ax.spines[side].set_linewidth(0.8 * size)
    ax.tick_params(colors=theme.muted, labelsize=8.5 * size, length=0)
    if title:
        ax.set_title(title, loc="left", fontsize=10.5 * size, color=theme.ink,
                     fontweight="semibold", pad=8)
    ax.set_xlabel(x_label, fontsize=9 * size, color=theme.ink_secondary)
    ax.set_ylabel("Correct answers", fontsize=9 * size, color=theme.ink_secondary)
    ax.figure.canvas.draw()
    _place_labels(ax, points, x_of, theme)


def figure(
    strategies: list[LearnedStrategyOutcome],
    prompts: int,
    subtitle: str,
    title: str,
    x_of: Callable[[Point], float],
    x_label: str,
    x_unit: tuple[str, str],
    out: Path,
    theme: Theme = LIGHT,
) -> list[Path]:
    """All four panels with a heading (docs), or the all-prompts panel alone (slides)."""
    slide = theme is SLIDE
    present = set(next(iter(strategies)).by_task) if strategies else set()
    panels = PANELS[:1] if slide else [
        (task, name) for task, name in PANELS if task is None or task in present
    ]
    fig, grid = plt.subplots(
        1 if slide else 2, 1 if slide else 2, figsize=(9.2, 6.3) if slide else (12, 8.2),
        facecolor=theme.surface, squeeze=False,
    )
    axes = list(grid.flat)
    for unused in axes[len(panels):]:  # a task group with no prompts gets no panel
        fig.delaxes(unused)
    axes = axes[: len(panels)]
    for ax, (task, name) in zip(axes, panels, strict=True):
        count = prompts if task is None else next(iter(strategies)).by_task[task].prompts
        _panel(ax, _points(strategies, task), x_of,
               "" if slide else f"{name} · {count} prompts", x_label, x_unit, theme)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", frameon=False, fontsize=9.5 * theme.scale,
               ncol=2, labelcolor=theme.ink_secondary,
               bbox_to_anchor=(0.985, 0.995 if slide else 0.985))
    if slide:
        fig.tight_layout(rect=(0, 0, 1, 0.93))
    else:
        fig.suptitle(title, x=0.015, y=0.975, ha="left", fontsize=13, color=theme.ink,
                     fontweight="semibold")
        fig.text(0.015, 0.935, subtitle, fontsize=9, color=theme.muted)
        fig.tight_layout(rect=(0, 0, 1, 0.92), h_pad=2.2, w_pad=2.5)
    for ax in axes:  # tight_layout moved the axes, so place the labels again
        for text in list(ax.texts):
            text.remove()
    fig.canvas.draw()
    for ax, (task, _) in zip(axes, panels, strict=True):
        _place_labels(ax, _points(strategies, task), x_of, theme)
    written = []
    for suffix in (".png", ".svg"):
        path = out.with_suffix(suffix)
        fig.savefig(path, dpi=160 if not slide else 220, facecolor=theme.surface,
                    metadata={"Date": None} if suffix == ".svg" else {"Software": None})
        written.append(path)
    plt.close(fig)
    return written


def write_pair(
    strategies: list[LearnedStrategyOutcome],
    prompts: int,
    subtitle: str,
    noun: str,
    stem: str,
    out_dir: Path,
    theme: Theme = LIGHT,
) -> list[Path]:
    """The accuracy-cost and accuracy-latency figures for one evaluation."""
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["svg.hashsalt"] = stem  # fixed element IDs, so reruns are identical
    written = figure(
        strategies, prompts, subtitle, f"Accuracy against cost on {noun}",
        lambda point: point.cost, "Total paid cost (USD)", ("$", ""),
        out_dir / f"{stem}-accuracy-cost", theme,
    )
    written += figure(
        strategies, prompts, subtitle, f"Accuracy against response time on {noun}",
        lambda point: point.latency_s, "Median latency (seconds)", ("", " s"),
        out_dir / f"{stem}-accuracy-latency", theme,
    )
    return written


# Robustness and priority sweep (week of Nov 26). Balanced has no panel of its own; the
# subtitle says so when it chooses as fastest does in every scenario.
PRIORITY_PANELS = [("quality", "Best quality"), ("cost", "Lowest cost"), ("latency", "Fastest")]
REFERENCE = "fixed_strongest"
# Multi-panel figures on a slide use a smaller step up than the one-panel comparison.
SLIDE_PANEL_SCALE = 1.3


@dataclass(frozen=True)
class Dumbbell:
    """One scenario in one priority panel: the router told about the change, the same router
    with its old estimates, and the always-strongest baseline (None where a result is missing)."""

    title: str
    observed: bool
    told: float | None
    old: float | None
    reference: float | None


def _dumbbells(
    report: RobustnessReport, priority: str, value: Callable[[ScenarioStrategy], float]
) -> list[Dumbbell]:
    rows = []
    for result in report.scenarios:
        found = {item.strategy_id: value(item) for item in result.strategies}
        rows.append(Dumbbell(
            result.scenario.title, result.scenario.observed, found.get(f"learned:{priority}"),
            found.get(f"learned_frozen:{priority}"), found.get(REFERENCE),
        ))
    return rows


def _balanced_matches_fastest(report: RobustnessReport) -> bool:
    def outcome(result_strategies: list[ScenarioStrategy], strategy_id: str) -> object:
        item = next((entry for entry in result_strategies if entry.strategy_id == strategy_id),
                    None)
        return None if item is None else (item.correct, item.total_cost_usd,
                                          item.median_latency_ms)

    return all(
        outcome(result.strategies, f"{kind}:balanced") == outcome(result.strategies,
                                                                  f"{kind}:latency")
        for result in report.scenarios
        for kind in ("learned", "learned_frozen")
    )


def _frame(
    ax: Axes, theme: Theme, grid_axis: Literal["both", "x", "y"], left_spine: bool = True
) -> None:
    """The comparison panels' look: hairline grid on one axis, two quiet spines, no ticks."""
    size = theme.scale
    ax.set_facecolor(theme.surface)
    ax.grid(True, axis=grid_axis, color=theme.grid, linewidth=0.8 * size, linestyle="-")
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    ax.spines["left"].set_visible(left_spine)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(theme.axis)
        ax.spines[side].set_linewidth(0.8 * size)
    ax.tick_params(colors=theme.muted, labelsize=8.5 * size, length=0)


def _dollars(value: float) -> str:
    if value >= 1:
        return f"${value:.0f}"
    return f"${value:.{max(0, round(-math.log10(value)))}f}"


def _cost_axis(ax: Axes, costs: list[float], theme: Theme) -> Callable[[float], float]:
    """A log axis for billed cost, with free ($0) drawn one decade left of the cheapest paid
    value, past a break in the axis line. Returns where a cost sits on the axis."""
    positive = [cost for cost in costs if cost > 0]
    low = math.floor(math.log10(min(positive))) if positive else -3
    zero = 10.0 ** (low - 1)
    right = (max(positive) if positive else 10.0**low) * 1.8
    ax.set_xscale("log")
    ax.set_xlim(zero / 10**0.35, right)
    ticks = [zero] + [10.0**power for power in range(low, math.floor(math.log10(right)) + 1)]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_minor_locator(NullLocator())
    ax.xaxis.set_major_formatter(FuncFormatter(
        lambda value, _: "$0" if value <= zero * 1.001 else _dollars(value)
    ))
    # The axis line breaks between $0 and the first decade, marked by two short slashes.
    size = theme.scale
    ax.spines["bottom"].set_visible(False)
    gap = (zero * 10**0.32, zero * 10**0.68)
    left, right_edge = ax.get_xlim()
    along_bottom = ax.get_xaxis_transform()
    for start, end in ((left, gap[0]), (gap[1], right_edge)):
        ax.plot([start, end], [0, 0], transform=along_bottom, color=theme.axis,
                linewidth=0.8 * size, solid_capstyle="butt", clip_on=False, zorder=5)
    ax.plot(list(gap), [0, 0], transform=along_bottom, linestyle="",
            marker=MarkerPath([(-1, -2), (1, 2)]), markersize=7 * size,
            markeredgewidth=0.9 * size, color=theme.muted, clip_on=False, zorder=5)
    return lambda cost: cost if cost > 0 else zero


def _dumbbell_panel(
    ax: Axes, rows: list[Dumbbell], position: Callable[[float], float], theme: Theme
) -> None:
    size = theme.scale
    for index, row in enumerate(rows):
        ring = theme.surface
        if row.observed:
            ax.axhspan(index - 0.5, index + 0.5, color=theme.band, linewidth=0, zorder=0.1)
            ring = theme.band
        if row.reference is not None:
            ax.scatter([position(row.reference)], [index], marker="|", s=150 * size * size,
                       color=theme.muted, alpha=0.6, linewidths=1.6 * size, zorder=2)
        if row.told is not None and row.old is not None:
            ax.plot([position(row.told), position(row.old)], [index, index], color=theme.axis,
                    linewidth=2 * size, solid_capstyle="round", zorder=2.5)
        # The square is drawn larger and underneath, so a shared spot still shows both.
        for value, marker, color, area, layer in (
            (row.old, "s", theme.baseline, 130, 3), (row.told, "o", theme.learned, 64, 4)
        ):
            if value is not None:
                ax.scatter([position(value)], [index], marker=marker, s=area * size * size,
                           color=color, edgecolors=ring, linewidths=2 * size, zorder=layer,
                           clip_on=False)


def _legend_handles(theme: Theme) -> list[Artist]:
    size = theme.scale
    return [
        Line2D([], [], marker="o", markersize=math.sqrt(64) * size, linestyle="",
               markerfacecolor=theme.learned, markeredgecolor=theme.surface,
               markeredgewidth=1.5 * size, label="Router told about the change"),
        Line2D([], [], marker="s", markersize=math.sqrt(130) * size, linestyle="",
               markerfacecolor=theme.baseline, markeredgecolor=theme.surface,
               markeredgewidth=1.5 * size, label="Same router, old estimates"),
        Line2D([], [], marker="|", markersize=math.sqrt(150) * size, linestyle="",
               color=theme.muted, alpha=0.6, markeredgewidth=1.6 * size,
               label="Always strongest model"),
        Patch(facecolor=theme.band, edgecolor=theme.grid, linewidth=0.8 * size,
              label="Change that really happened"),
    ]


def _heading(fig: Figure, title: str, subtitle: str, theme: Theme) -> None:
    """Title and subtitle at fixed distances from the top edge, whatever the figure height."""
    height = fig.get_figheight()
    fig.suptitle(title, x=0.015, y=1 - 0.2 / height, ha="left", fontsize=13, color=theme.ink,
                 fontweight="semibold")
    fig.text(0.015, 1 - 0.53 / height, subtitle, fontsize=9, color=theme.muted)


def _save(fig: Figure, out: Path, theme: Theme, slide: bool) -> list[Path]:
    written = []
    for suffix in (".png", ".svg"):
        path = out.with_suffix(suffix)
        fig.savefig(path, dpi=220 if slide else 160, facecolor=theme.surface,
                    metadata={"Date": None} if suffix == ".svg" else {"Software": None})
        written.append(path)
    plt.close(fig)
    return written


def robustness_figure(
    report: RobustnessReport,
    measure: str,
    title: str,
    subtitle: str,
    out: Path,
    theme: Theme = LIGHT,
) -> list[Path]:
    """One row per scenario and one panel per priority; ``measure`` is "correct" or "cost"."""
    slide = theme is SLIDE
    style = replace(theme, scale=SLIDE_PANEL_SCALE) if slide else theme
    size = style.scale
    cost = measure == "cost"

    def value(item: ScenarioStrategy) -> float:
        return item.total_cost_usd if cost else float(item.correct)

    panels = [
        (name, _dumbbells(report, priority, value)) for priority, name in PRIORITY_PANELS
    ]
    count = len(report.scenarios)
    height = 0.55 * count + 3.0 if slide else 0.42 * count + 2.7
    fig, grid = plt.subplots(1, len(panels), sharey=True, squeeze=False,
                             figsize=(15.5 if slide else 13, height), facecolor=style.surface)
    axes = list(grid.flat)
    values = [
        point for _, rows in panels for row in rows
        for point in (row.told, row.old, row.reference) if point is not None
    ]
    for ax, (name, rows) in zip(axes, panels, strict=True):
        _frame(ax, style, "x", left_spine=False)
        position: Callable[[float], float] = _same
        if cost:
            position = _cost_axis(ax, values, style)
            label = f"Billed cost for {report.prompts} prompts (USD, log scale)"
        else:
            low = min(values, default=0.0)
            ax.set_xlim(max(0.0, low - 0.06 * (report.prompts - low)), report.prompts * 1.02)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10],
                                                   integer=True))
            label = f"Right answers (of {report.prompts})"
        _dumbbell_panel(ax, rows, position, style)
        ax.set_title(name, loc="left", fontsize=10.5 * size, color=style.ink,
                     fontweight="semibold", pad=8)
        ax.set_xlabel(label, fontsize=9 * size, color=style.ink_secondary)
    first_rows = panels[0][1]
    axes[0].set_ylim(count - 0.5, -0.5)
    axes[0].set_yticks(range(count))
    axes[0].set_yticklabels([row.title for row in first_rows], fontsize=9 * size,
                            color=style.ink_secondary)
    for tick, row in zip(axes[0].get_yticklabels(), first_rows, strict=True):
        if row.observed:
            tick.set_color(style.ink)
            tick.set_fontweight("semibold")
    legend_top = 0.15 if slide else 0.68  # inches below the top edge
    fig.legend(handles=_legend_handles(style), loc="upper left", frameon=False,
               fontsize=9.5 * size, ncol=4, labelcolor=style.ink_secondary,
               bbox_to_anchor=(0.008, 1 - legend_top / height), columnspacing=2.0)
    fig.tight_layout(rect=(0, 0, 1, 1 - (legend_top + 0.4 * size) / height), w_pad=2.5)
    if not slide:  # after the layout, which would otherwise make room for the title twice
        _heading(fig, title, subtitle, style)
    return _save(fig, out, style, slide)


def _same(value: float) -> float:
    return value


def _billed(point: PrioritySweepPoint) -> float:
    return point.total_cost_usd


def _seconds(point: PrioritySweepPoint) -> float:
    return (point.median_latency_ms or 0.0) / 1000


def _sweep_labels(
    ax: Axes, xs: list[float], ys: list[float], weights: list[float], theme: Theme
) -> tuple[list[Point], list[Bbox]]:
    """One label per spot as drawn: consecutive sweep points within a marker of each other
    share a label, the range of their weights. Returns the labeled points (x position kept in
    ``Point.cost``) and the boxes the labels must avoid: the other markers and the line."""
    shown = [
        (float(x), float(y))
        for x, y in (ax.transData.transform((x, y)) for x, y in zip(xs, ys, strict=True))
    ]
    reach = 7 * theme.scale
    groups: list[list[int]] = []
    for index, here in enumerate(shown):
        if groups and math.dist(here, shown[groups[-1][0]]) <= reach:
            groups[-1].append(index)
        else:
            groups.append([index])
    points = []
    for group in groups:
        first, last = f"{weights[group[0]]:g}", f"{weights[group[-1]]:g}"
        text = first if first == last else f"{first}–{last}"
        points.append(Point(f"w = {text}", True, ys[group[0]], xs[group[0]], 0.0))
    obstacles = [
        Bbox.from_extents(x - reach, y - reach, x + reach, y + reach)
        for group in groups for x, y in (shown[index] for index in group[1:])
    ]
    half = 1.5 * theme.scale
    for (x0, y0), (x1, y1) in zip(shown, shown[1:], strict=False):
        steps = max(1, int(math.dist((x0, y0), (x1, y1)) // (2 * half)))
        for step in range(steps + 1):
            x, y = x0 + (x1 - x0) * step / steps, y0 + (y1 - y0) * step / steps
            obstacles.append(Bbox.from_extents(x - half, y - half, x + half, y + half))
    return points, obstacles


def sweep_figure(
    report: RobustnessReport, title: str, subtitle: str, out: Path, theme: Theme = LIGHT
) -> list[Path]:
    """Accuracy against billed cost as the cost weight rises, and against median time as the
    latency weight rises (the quality weight stays 1, the others 0)."""
    slide = theme is SLIDE
    style = replace(theme, scale=SLIDE_PANEL_SCALE) if slide else theme
    size = style.scale
    height = 7.0 if slide else 5.6
    fig, grid = plt.subplots(1, 2, sharey=True, squeeze=False,
                             figsize=(14 if slide else 12, height), facecolor=style.surface)
    axes = list(grid.flat)
    placed: list[tuple[Axes, list[float], list[float], list[float]]] = []
    accuracies = [point.accuracy * 100 for point in report.priority_sweep]
    for ax, axis in zip(axes, ("cost", "latency"), strict=True):
        sweep = sorted(
            (point for point in report.priority_sweep
             if point.axis == axis and (axis == "cost" or point.median_latency_ms is not None)),
            key=lambda point: point.weight,
        )
        _frame(ax, style, "both")
        raw = _billed if axis == "cost" else _seconds
        position: Callable[[float], float] = _same
        if axis == "cost":
            position = _cost_axis(ax, [raw(point) for point in sweep], style)
            label = f"Billed cost for {report.prompts} prompts (USD, log scale)"
        else:
            ax.set_xlim(0, max((raw(point) for point in sweep), default=1.0) * 1.25)
            ax.xaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
            ax.xaxis.set_major_formatter(FuncFormatter(
                lambda value, _: "" if value < 0 else f"{value:g} s"
            ))
            label = "Median latency (seconds)"
        xs = [position(raw(point)) for point in sweep]
        ys = [point.accuracy * 100 for point in sweep]
        ax.plot(xs, ys, color=style.learned, linewidth=2 * size, solid_joinstyle="round",
                solid_capstyle="round", zorder=2)
        ax.scatter(xs, ys, s=70 * size * size, marker="o", color=style.learned,
                   edgecolors=style.surface, linewidths=2 * size, zorder=3, clip_on=False)
        weights = [point.weight for point in sweep]
        span = f" from {min(weights):g} to {max(weights):g}" if weights else ""
        ax.set_title(f"{axis.capitalize()} weight w{span}", loc="left", fontsize=10.5 * size,
                     color=style.ink, fontweight="semibold", pad=8)
        ax.set_xlabel(label, fontsize=9 * size, color=style.ink_secondary)
        placed.append((ax, xs, ys, weights))
    low, high = min(accuracies, default=0.0), max(accuracies, default=100.0)
    axes[0].set_ylim(max(0.0, low - 1.5), min(100.0, high + 2.0))
    axes[0].yaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
    axes[0].yaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:.0f}%"))
    axes[0].set_ylabel("Correct answers", fontsize=9 * size, color=style.ink_secondary)
    fig.tight_layout(rect=(0, 0, 1, 1 - (0.1 if slide else 0.75) / height), w_pad=3.0)
    if not slide:
        _heading(fig, title, subtitle, style)
    fig.canvas.draw()  # labels are placed in the final layout's pixels
    for ax, xs, ys, weights in placed:
        points, obstacles = _sweep_labels(ax, xs, ys, weights, style)
        _place_labels(ax, points, lambda point: point.cost, style, skip_crowded=True,
                      obstacles=obstacles)
    return _save(fig, out, style, slide)


# The scenarios the scoring fix was built for: (scenario, priority, extra measure, panel title).
FIX_SCENARIOS = [
    ("ovh_latency_x3", "latency", "time", "Slowest three models 3x slower, fastest setting"),
    ("gemini_price_x4", "cost", "cost", "Most expensive model 4x pricier, lowest-cost setting"),
    ("free_outage_50", "cost", "cost", "Free remote models fail 50%, lowest-cost setting"),
    ("gemma_mercury_unavailable", "latency", "time",
     "Gemma 4 26B and Mercury 3 unavailable, fastest setting"),
]
FIX_ROWS = ("Frozen scoring", "Fixed scoring")


def _fix_dumbbells(
    evaluation: ScoringFixEvaluation, scenario_id: str, priority: str,
    value: Callable[[ScenarioStrategy], float],
) -> list[Dumbbell]:
    rows = []
    for report in (evaluation.frozen, evaluation.fixed):
        result = next(item for item in report.scenarios
                      if item.scenario.scenario_id == scenario_id)
        found = {item.strategy_id: value(item) for item in result.strategies}
        rows.append(Dumbbell(
            result.scenario.title, result.scenario.observed, found[f"learned:{priority}"],
            found[f"learned_frozen:{priority}"], None,
        ))
    return rows


def scoring_fix_figure(
    evaluation: ScoringFixEvaluation, title: str, subtitle: str, out: Path, theme: Theme = LIGHT
) -> list[Path]:
    """Frozen and fixed scoring, told and with old estimates, in each scenario the fix targets:
    right answers on the left, then median time or billed cost on the right."""
    slide = theme is SLIDE
    style = replace(theme, scale=SLIDE_PANEL_SCALE) if slide else theme
    size = style.scale
    count = len(FIX_SCENARIOS)
    height = 1.45 * count + 2.0 if slide else 1.15 * count + 1.9
    fig, grid = plt.subplots(count, 2, sharey=True, squeeze=False,
                             figsize=(15.5 if slide else 13, height), facecolor=style.surface)
    for row_index, (scenario_id, priority, extra, panel_title) in enumerate(FIX_SCENARIOS):
        measures: list[tuple[str, Callable[[ScenarioStrategy], float]]] = [
            ("correct", lambda item: float(item.correct)),
            (extra, (lambda item: item.total_cost_usd) if extra == "cost"
             else (lambda item: (item.median_latency_ms or 0.0) / 1000)),
        ]
        for column, (measure, value) in enumerate(measures):
            ax = grid[row_index][column]
            rows = _fix_dumbbells(evaluation, scenario_id, priority, value)
            numbers = [point for row in rows for point in (row.told, row.old)
                       if point is not None]
            _frame(ax, style, "x", left_spine=False)
            position: Callable[[float], float] = _same
            if measure == "cost":
                position = _cost_axis(ax, numbers, style)
                label = f"Billed cost for {evaluation.prompts} prompts (USD, log scale)"
            elif measure == "time":
                ax.set_xlim(0, max(numbers) * 1.2)
                ax.xaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10]))
                ax.xaxis.set_major_formatter(FuncFormatter(
                    lambda tick, _: "" if tick < 0 else f"{tick:g} s"
                ))
                label = "Median time (seconds)"
            else:
                low, high = min(numbers), max(numbers)
                pad = max(2.0, 0.08 * (high - low))
                ax.set_xlim(low - pad, min(float(evaluation.prompts), high + pad))
                ax.xaxis.set_major_locator(MaxNLocator(nbins=6, steps=[1, 2, 2.5, 5, 10],
                                                       integer=True))
                label = f"Right answers (of {evaluation.prompts})"
            _dumbbell_panel(ax, rows, position, style)
            if column == 0:
                ax.set_title(panel_title, loc="left", fontsize=10 * size, color=style.ink,
                             fontweight="semibold", pad=6)
            ax.set_xlabel(label, fontsize=8.5 * size, color=style.ink_secondary)
    axes = [grid[index][0] for index in range(count)]
    axes[0].set_ylim(1.5, -0.5)
    axes[0].set_yticks(range(len(FIX_ROWS)))
    for ax in axes:
        ax.set_yticklabels(FIX_ROWS, fontsize=9 * size, color=style.ink_secondary)
    handles = [handle for handle in _legend_handles(style)
               if handle.get_label() != "Always strongest model"]
    legend_top = 0.15 if slide else 0.68
    fig.legend(handles=handles, loc="upper left", frameon=False, fontsize=9.5 * size, ncol=3,
               labelcolor=style.ink_secondary,
               bbox_to_anchor=(0.008, 1 - legend_top / height), columnspacing=2.0)
    fig.tight_layout(rect=(0, 0, 1, 1 - (legend_top + 0.4 * size) / height), w_pad=2.5,
                     h_pad=1.2)
    if not slide:
        _heading(fig, title, subtitle, style)
    return _save(fig, out, style, slide)


def write_scoring_fix(
    report: ScoringFixReport, out_dir: Path, theme: Theme = LIGHT
) -> list[Path]:
    """The scoring-fix figure for the fresh prompts."""
    fresh = next(item for item in report.evaluations if item.evaluation_id == "final")
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams["svg.fonttype"] = "none"
    plt.rcParams["svg.hashsalt"] = "scoring-fix-robustness"
    subtitle = (
        f"{fresh.prompts} fresh prompts, replayed under each change. The fixed scoring divides "
        "cost and time by fixed references and weighs reliability; the frozen router does not."
    )
    return scoring_fix_figure(
        fresh, "Fixing the scoring flaw: right answers, time and cost under change", subtitle,
        out_dir / "scoring-fix-robustness", theme,
    )


def write_robustness(
    report: FinalEvaluationReport, out_dir: Path, theme: Theme = LIGHT
) -> list[Path]:
    """The robustness and priority-sweep figures for the fresh prompts."""
    fresh = next((item for item in report.robustness if item.evaluation_id == "final"), None)
    if fresh is None:
        raise ValueError("The report has no robustness results for the fresh prompts")
    out_dir.mkdir(parents=True, exist_ok=True)
    plt.rcParams["svg.fonttype"] = "none"
    balanced = (" Balanced matches fastest in every scenario."
                if _balanced_matches_fastest(fresh) else "")
    subtitle = (
        f"{fresh.prompts} fresh prompts, replayed under each change. Hypothetical changes come "
        f"on top of the live catalog of 2026-11-13.{balanced}"
    )
    written = []
    for stem, measure, noun in (
        ("final-robustness", "correct", "Right answers"),
        ("final-robustness-cost", "cost", "Billed cost"),
    ):
        plt.rcParams["svg.hashsalt"] = stem  # fixed element IDs, so reruns are identical
        written += robustness_figure(
            fresh, measure, f"{noun} when conditions change, on the fresh prompts", subtitle,
            out_dir / stem, theme,
        )
    plt.rcParams["svg.hashsalt"] = "final-priority-sweep"
    written += sweep_figure(
        fresh, "Trading accuracy for cost and for speed, on the fresh prompts",
        f"{fresh.prompts} fresh prompts. The quality weight stays 1 while one other weight w "
        "rises and the rest stay 0; points are labeled with w where the label fits.",
        out_dir / "final-priority-sweep", theme,
    )
    return written


def write_all(
    out_dir: Path,
    theme: Theme = LIGHT,
    report_path: Path = REPORT_PATH,
    final_report_path: Path = FINAL_REPORT_PATH,
    scoring_fix_path: Path = SCORING_FIX_PATH,
) -> list[Path]:
    """Every figure this module draws, from the committed reports."""
    report = LearnedRouterReport.model_validate_json(report_path.read_text(encoding="utf-8"))
    held = report.heldout
    subtitle = (
        f"Held-out test split, read once. Router {held.artifact_id}, trained on "
        f"{' + '.join(held.trained_on)}; outcomes replayed from the saved matrix."
    )
    written = write_pair(
        held.strategies, held.prompts, subtitle, "held-out prompts", "cp3-heldout",
        out_dir, theme,
    )
    final = FinalEvaluationReport.model_validate_json(
        final_report_path.read_text(encoding="utf-8")
    )
    fix = ScoringFixReport.model_validate_json(scoring_fix_path.read_text(encoding="utf-8"))
    return written + write_robustness(final, out_dir, theme) + write_scoring_fix(
        fix, out_dir, theme
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", type=Path, default=REPORT_PATH)
    parser.add_argument("--final-report", type=Path, default=FINAL_REPORT_PATH)
    parser.add_argument("--scoring-fix-report", type=Path, default=SCORING_FIX_PATH)
    parser.add_argument("--slides", type=Path, help="Write the dark slide versions here")
    args = parser.parse_args(argv)
    theme, out_dir = (SLIDE, args.slides) if args.slides else (LIGHT, FIGURE_DIR)
    for path in write_all(out_dir, theme, args.report, args.final_report,
                          args.scoring_fix_report):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
