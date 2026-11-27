"""The scoring fix, tested (week of Dec 3): fixed cost and time references, small reliability.

    uv run --project backend python -m app.learned.scoring_fix

Robustness testing exposed two flaws in the frozen router's scoring (docs/checkpoint-4-progress.md):

- cost and time are divided by the largest value among the available models, so when the most
  expensive (or slowest) model changes, every other model's score shifts and the user's setting
  moves the wrong way;
- the tuned presets give reliability no weight, so a failing model is not avoided.

The frozen router stays the evaluated system and no committed file changes. This module tests a
variant that has the same classifier and features, divides cost and time by fixed references
(the frozen estimates' largest expected cost and time per task group), and gives reliability a
small default weight chosen on the Checkpoint 3 validation split with the frozen recipe.

Nothing is tuned on the fresh prompts, which are read again here. Every number is offline replay
of the committed cell table (no provider is called), and the report goes to
``data/learned/scoring-fix-study.json``.
"""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from typing import Any

from app.benchmarks.suite import RouterSplit
from app.benchmarks.suite_runner import FINAL_PATH
from app.config import REPOSITORY_ROOT
from app.domain.models import (
    LiveCatalogStatus,
    PairedComparison,
    RobustnessReport,
    RoutingPriority,
    RoutingWeights,
    ScenarioSpec,
    ScenarioStrategy,
)
from app.domain.scoring_fix import (
    EvidenceRow,
    QuestionAnswer,
    ScoringFixEvaluation,
    ScoringFixReport,
    ScoringFixTuning,
)
from app.learned import stats
from app.learned.evaluate import CHEAPEST, FASTEST, STRONGEST, complete_prompts, routing_estimates
from app.learned.evaluate import tune_weights as tune
from app.learned.features import ModelHistory
from app.learned.final_eval import (
    CATALOG_PATH,
    CELLS_PATH,
    Suite,
    _sha256,
    complete,
    load_suites,
)
from app.learned.robustness import (
    Knowledge,
    RouterView,
    World,
    _weights,
    catalog_knowledge,
    retired_call_latency,
    run_scenarios,
    standard_scenarios,
)
from app.learned.router import (
    ROUTER_MODEL_PATH,
    LearnedRouter,
    ScoringReference,
    load_router,
)
from app.learned.train import (
    FAMILY_FACTORIES,
    POOL_PATH,
    TRAIN_ONLY,
    build_dataset,
    matrix_summary,
)
from app.registry.pool import load_pool

REPORT_PATH = REPOSITORY_ROOT / "data" / "learned" / "scoring-fix-study.json"
SCENARIO_NO_CHANGE = "no_change"
SCENARIO_GEMMA_GONE = "gemma_mercury_unavailable"
# The reliability weights the fixed variant's tuning may choose from: the frozen grid was
# (0.0, 0.5); the floor replaces its zero, so the preset cannot ignore failures. Fixed on
# 2026-11-26 before any result of the fixed variant was read.
RELIABILITY_FLOOR = 0.25
FIXED_RELIABILITY_GRID = (RELIABILITY_FLOOR, 0.5)
SIGNIFICANT = 0.05


@dataclass(frozen=True)
class FixedQuestion:
    question_id: str
    question: str
    rule: str  # how the answer is decided, from the numbers alone


# Fixed on 2026-11-26, before any result of the fixed variant was read. "Told" is the router
# that learns the change (live catalog, call monitoring); "old estimates" is the router that
# keeps its trained estimates. Both use the same presets and the same changed world.
FIXED_QUESTIONS: tuple[FixedQuestion, ...] = (
    FixedQuestion(
        "keeps_accuracy",
        "With no change, does the fixed scoring keep accuracy on the fresh prompts at each "
        "priority?",
        "Yes if no priority has fewer right answers than the frozen router with a Holm-adjusted "
        f"McNemar p below {SIGNIFICANT} (four priorities, one family with the scenario tests).",
    ),
    FixedQuestion(
        "fastest_faster_when_told",
        "In 'slowest three models 3x slower', does the fastest setting get faster (median time) "
        "when told, unlike the frozen router?",
        "Yes if the fixed variant's median time when told is below its median time with old "
        "estimates.",
    ),
    FixedQuestion(
        "expensive_price_x4",
        "In 'most expensive model 4x pricier', does the lowest-cost setting stop shifting spend "
        "to other models, and does best quality reduce its use of that model?",
        "Yes if, told rather than with old estimates, the lowest-cost setting sends at most 5 "
        "percentage points more prompts to Gemma 4 26B and spends at most twice as much, and "
        "best quality sends fewer prompts to Gemini 4 Argon.",
    ),
    FixedQuestion(
        "outage_holds_accuracy",
        "In 'free remote models fail 50%', does the lowest-cost setting hold its accuracy when "
        "told, without a hand-raised weight?",
        "Yes if, told, it keeps at least 95% of its right answers with nothing changed and gets "
        "more right than with old estimates.",
    ),
)

# Which scenario and priority each question looks at, per router: (scenario_id, priority).
QUESTION_CASES: dict[str, tuple[tuple[str, RoutingPriority], ...]] = {
    "fastest_faster_when_told": (("ovh_latency_x3", RoutingPriority.LATENCY),),
    "expensive_price_x4": (
        ("gemini_price_x4", RoutingPriority.COST),
        ("gemini_price_x4", RoutingPriority.QUALITY),
    ),
    "outage_holds_accuracy": (("free_outage_50", RoutingPriority.COST),),
}
ROUTERS = ("frozen", "fixed")


def scoring_fix_scenarios(
    models: list[str], *, gemma_price_ratio: float, drift_in_world: bool
) -> list[ScenarioSpec]:
    """Every existing scenario, a no-change reference, and the observed Gemma and Mercury one."""
    no_change = ScenarioSpec(
        scenario_id=SCENARIO_NO_CHANGE,
        title="No change",
        condition="none",
        observed=False,
        description="Nothing changes: the router as it would be deployed, as the reference for "
        "every other scenario.",
        world_already_changed=drift_in_world,
    )
    gemma_gone = ScenarioSpec(
        scenario_id=SCENARIO_GEMMA_GONE,
        title="Gemma 4 26B and Mercury 3 unavailable",
        condition="availability",
        observed=True,
        description="On 2026-11-26 the live catalog check found Gemma 4 26B A4B no longer served "
        "by its pinned host (NextBit), after Mercury 3's retirement on 2026-11-12. The router "
        "that is told excludes both; with old estimates it still sends prompts to them, and "
        "those calls fail. Calls to a model that went away are replayed as failures after 0.4 s "
        "(Mercury's real 404 time). On the fresh prompts, the router with old estimates still "
        "has the 2026-11-13 catalog, so Mercury 3 is already excluded.",
        unavailable=[CHEAPEST, FASTEST],
    )
    existing = standard_scenarios(
        models, gemma_price_ratio=gemma_price_ratio, drift_in_world=drift_in_world
    )
    observed = [item for item in existing if item.observed]
    return [no_change, *observed, gemma_gone, *(item for item in existing if not item.observed)]


def fixed_presets(tuning: ScoringFixTuning) -> dict[RoutingPriority, RoutingWeights]:
    return {item.priority: item.weights for item in tuning.fixed_presets}


def tune_fixed_variant(
    router: LearnedRouter, suite: Suite
) -> tuple[ScoringFixTuning, ScoringReference]:
    """Re-tune the presets on the validation split alone, as the frozen router's were.

    The frozen classifier was refit on training and validation, so its validation predictions
    are in-sample. Like the original tuning, this refits the same family on the training split
    alone (same regularization) and tunes on its validation predictions, with training-split
    estimates. The old recipe is rerun first to check that this reproduces the frozen presets.
    """
    cells, items = suite.cells, suite.items
    models = router.models
    history = ModelHistory(cells)
    train = build_dataset(RouterSplit.TRAIN, cells, items, models, history)
    validation = build_dataset(RouterSplit.VALIDATION, cells, items, models, history)
    classifier = FAMILY_FACTORIES[router.artifact.family]()
    classifier.set_params(**router.artifact.params)
    classifier.fit(train.x, train.y)
    probability = validation.probability(classifier.predict_proba(validation.x)[:, 1])
    estimates = routing_estimates(cells, TRAIN_ONLY)
    prompts = complete_prompts(cells, RouterSplit.VALIDATION, sorted(models))
    reference = ScoringReference.from_estimates(estimates)
    ids = sorted(models)
    recipe_check = tune(prompts, probability, estimates, ids, cells, items)
    reproduced = all(
        mine.weights == router.artifact.weights[mine.priority] for mine in recipe_check
    )
    reference_only = tune(prompts, probability, estimates, ids, cells, items, reference=reference)
    fixed = tune(
        prompts, probability, estimates, ids, cells, items, reference=reference,
        reliability_grid=FIXED_RELIABILITY_GRID,
    )
    chosen = ", ".join(
        f"{item.priority.value} {item.weights.reliability:g}" for item in fixed
    )
    tuning = ScoringFixTuning(
        classifier=router.artifact.artifact_id,
        validation_prompts=len(prompts),
        reliability_floor=RELIABILITY_FLOOR,
        reliability_grid=list(FIXED_RELIABILITY_GRID),
        tuning_reference=reference,
        frozen_recipe_reproduced=reproduced,
        recipe_check_presets=recipe_check,
        reference_only_presets=reference_only,
        fixed_presets=fixed,
        note=(
            "Presets are re-tuned per priority on the validation split alone, with the frozen "
            "recipe's grids, accuracy floors and tie-breaks. The reliability grid replaces "
            f"0 with the floor {RELIABILITY_FLOOR:g}, so it is {FIXED_RELIABILITY_GRID}; "
            f"the chosen reliability weights are {chosen}. Cost and time use fixed "
            "references, here the training-split estimates' largest expected cost and time per "
            "task group. In an unchanged pool those equal the largest among the available "
            "models, so the fixed scoring differs from the frozen one only through the "
            "reliability weight and when a model's price, speed or availability changes."
        ),
    )
    return tuning, reference


def _evidence(
    evaluation_id: str,
    reports: dict[str, RobustnessReport],
    scenario_id: str,
    priority: RoutingPriority,
    router: str,
    p_value: float | None,
) -> EvidenceRow:
    report = reports[router]

    def find(scenario: str, strategy: str) -> ScenarioStrategy:
        result = next(item for item in report.scenarios if item.scenario.scenario_id == scenario)
        return next(item for item in result.strategies if item.strategy_id == strategy)

    label = priority.value
    return EvidenceRow(
        evaluation_id=evaluation_id,
        scenario_id=scenario_id,
        priority=priority,
        router=router,
        told=find(scenario_id, f"learned:{label}"),
        old=find(scenario_id, f"learned_frozen:{label}"),
        unchanged=find(SCENARIO_NO_CHANGE, f"learned:{label}"),
        told_vs_old_p=p_value,
    )


def _pick_outcomes(
    view: RouterView,
    world: World,
    prompts: list[str],
    spec: ScenarioSpec | None,
    knowledge: Knowledge,
    weights: RoutingWeights,
    reference: ScoringReference | None,
) -> tuple[dict[str, str], stats.Outcomes]:
    picks = {sample: view.choose(sample, weights, knowledge, reference) for sample in prompts}
    rows = [world.outcome(sample, model, spec)[:3] for sample, model in picks.items()]
    return picks, stats.Outcomes.from_rows(rows)


def _knowledge_pair(spec: ScenarioSpec, base: Knowledge) -> tuple[Knowledge, Knowledge]:
    """What the told and the old-estimates routers know (as ``run_scenarios`` does)."""
    change = Knowledge.from_scenario(spec)
    if spec.world_already_changed:
        return base, base.minus(change)
    return base.plus(change), base


def paired_tests(
    view: RouterView,
    world: World,
    prompts: list[str],
    specs: dict[str, ScenarioSpec],
    base: Knowledge,
    presets: dict[str, dict[RoutingPriority, RoutingWeights]],
    reference: ScoringReference,
) -> list[PairedComparison]:
    """The questions' paired tests, in one Holm family: fixed vs frozen with nothing changed,
    and each router told vs with old estimates in the question scenarios."""
    indices = stats.bootstrap_indices(len(prompts))
    comparisons = []
    for priority in RoutingPriority:
        _, fixed = _pick_outcomes(
            view, world, prompts, None, base, presets["fixed"][priority], reference
        )
        _, frozen = _pick_outcomes(
            view, world, prompts, None, base, presets["frozen"][priority], None
        )
        comparisons.append(stats.compare(
            f"fixed:{priority.value}", f"frozen:{priority.value}",
            "With nothing changed, does the fixed scoring answer as many right as the frozen "
            "router?", fixed, frozen, indices,
        ))
    for cases in QUESTION_CASES.values():
        for scenario_id, priority in cases:
            spec = specs[scenario_id]
            told_knowledge, old_knowledge = _knowledge_pair(spec, base)
            for router in ROUTERS:
                weights = _weights(presets[router][priority], spec)
                scoring = reference if router == "fixed" else None
                _, told = _pick_outcomes(
                    view, world, prompts, spec, told_knowledge, weights, scoring
                )
                _, old = _pick_outcomes(
                    view, world, prompts, spec, old_knowledge, weights, scoring
                )
                comparisons.append(stats.compare(
                    f"{router}:{priority.value}:{scenario_id}:told",
                    f"{router}:{priority.value}:{scenario_id}:old",
                    f"{spec.title}: does the {router} router get more right when told?",
                    told, old, indices,
                ))
    return stats.adjust(comparisons)


def _p(
    comparisons: list[PairedComparison], router: str, priority: RoutingPriority, scenario: str
) -> float | None:
    wanted = f"{router}:{priority.value}:{scenario}:told"
    return next((item.holm_p for item in comparisons if item.strategy_id == wanted), None)


def _count(row: EvidenceRow, model: str, which: str) -> int:
    strategy = row.told if which == "told" else row.old
    return strategy.selected_models.get(model, 0)


def _seconds(milliseconds: float | None) -> str:
    return "n/a" if milliseconds is None else f"{milliseconds / 1000:.2f} s"


def _money(value: float) -> str:
    return "$0" if value == 0 else f"${value:.4f}" if value < 0.1 else f"${value:.2f}"


def _fastest_faster(evidence: list[EvidenceRow]) -> tuple[bool, str]:
    frozen = next(row for row in evidence if row.router == "frozen")
    fixed = next(row for row in evidence if row.router == "fixed")
    holds = (
        fixed.told.median_latency_ms is not None
        and fixed.old.median_latency_ms is not None
        and fixed.told.median_latency_ms < fixed.old.median_latency_ms
    )
    return holds, (
        f"Fixed scoring, told: {_seconds(fixed.told.median_latency_ms)} median "
        f"({fixed.told.correct} right, {_money(fixed.told.total_cost_usd)}) against "
        f"{_seconds(fixed.old.median_latency_ms)} with old estimates "
        f"({fixed.old.correct} right, {_money(fixed.old.total_cost_usd)}); with nothing "
        f"changed it takes {_seconds(fixed.unchanged.median_latency_ms)}. Frozen router, told: "
        f"{_seconds(frozen.told.median_latency_ms)} against "
        f"{_seconds(frozen.old.median_latency_ms)}."
    )


def _price_x4(evidence: list[EvidenceRow], prompts: int) -> tuple[bool, str]:
    def pick(router: str, priority: RoutingPriority) -> EvidenceRow:
        return next(
            row for row in evidence if row.router == router and row.priority == priority
        )

    cost, quality = pick("fixed", RoutingPriority.COST), pick("fixed", RoutingPriority.QUALITY)
    frozen_cost = pick("frozen", RoutingPriority.COST)
    frozen_quality = pick("frozen", RoutingPriority.QUALITY)
    share_told = _count(cost, CHEAPEST, "told") / prompts
    share_old = _count(cost, CHEAPEST, "old") / prompts
    steady = (
        share_told <= share_old + 0.05
        and cost.told.total_cost_usd <= 2 * cost.old.total_cost_usd
    )
    fewer = _count(quality, STRONGEST, "told") < _count(quality, STRONGEST, "old")
    return steady and fewer, (
        f"Lowest cost, fixed scoring: {_count(cost, CHEAPEST, 'told')} prompts to Gemma 4 26B "
        f"when told against {_count(cost, CHEAPEST, 'old')} with old estimates, spending "
        f"{_money(cost.told.total_cost_usd)} against {_money(cost.old.total_cost_usd)} "
        f"(frozen: {_count(frozen_cost, CHEAPEST, 'told')} against "
        f"{_count(frozen_cost, CHEAPEST, 'old')}, {_money(frozen_cost.told.total_cost_usd)} "
        f"against {_money(frozen_cost.old.total_cost_usd)}). Best quality, fixed scoring: "
        f"{_count(quality, STRONGEST, 'told')} prompts to Gemini 4 Argon when told against "
        f"{_count(quality, STRONGEST, 'old')} (frozen: "
        f"{_count(frozen_quality, STRONGEST, 'told')} against "
        f"{_count(frozen_quality, STRONGEST, 'old')}), {quality.told.correct} right for "
        f"{_money(quality.told.total_cost_usd)} against {quality.old.correct} for "
        f"{_money(quality.old.total_cost_usd)} (Holm p "
        f"{'n/a' if quality.told_vs_old_p is None else f'{quality.told_vs_old_p:.2g}'}): "
        "the best-quality setting reacts fully to the price, at a cost in right answers."
    )


def _outage(evidence: list[EvidenceRow]) -> tuple[bool, str]:
    frozen = next(row for row in evidence if row.router == "frozen")
    fixed = next(row for row in evidence if row.router == "fixed")
    holds = (
        fixed.told.correct >= 0.95 * fixed.unchanged.correct
        and fixed.told.correct > fixed.old.correct
    )
    return holds, (
        f"Lowest cost, fixed scoring: {fixed.told.correct} right when told, "
        f"{fixed.old.correct} with old estimates, {fixed.unchanged.correct} with no outage "
        f"({_money(fixed.told.total_cost_usd)} told). Frozen router: {frozen.told.correct} told, "
        f"{frozen.old.correct} old, {frozen.unchanged.correct} with no outage."
    )


def _keeps_accuracy(
    comparisons: list[PairedComparison], reports: dict[str, RobustnessReport]
) -> tuple[bool, str]:
    del reports
    firsts = [item for item in comparisons if item.strategy_id.count(":") == 1]
    worse = [
        item for item in firsts
        if item.correct < item.baseline_correct and item.holm_p < SIGNIFICANT
    ]
    detail = "; ".join(
        f"{item.strategy_id.split(':')[1]} {item.correct} against {item.baseline_correct} "
        f"(Holm p {item.holm_p:.3f}, spend {'+' if item.cost_difference_usd >= 0 else '-'}"
        f"{_money(abs(item.cost_difference_usd))})"
        for item in firsts
    )
    return not worse, f"Fixed against frozen, right answers and change in spend: {detail}."


def answer_questions(
    evaluations: dict[str, dict[str, Any]],
) -> list[QuestionAnswer]:
    """Answer each fixed question from the numbers, on the fresh prompts and the test split."""
    answers = []
    for question in FIXED_QUESTIONS:
        verdicts: dict[str, bool] = {}
        texts: dict[str, str] = {}
        evidence: list[EvidenceRow] = []
        for evaluation_id, data in evaluations.items():
            comparisons: list[PairedComparison] = data["comparisons"]
            reports: dict[str, RobustnessReport] = data["reports"]
            rows = [
                _evidence(evaluation_id, reports, scenario_id, priority, router,
                          _p(comparisons, router, priority, scenario_id))
                for scenario_id, priority in QUESTION_CASES.get(question.question_id, ())
                for router in ROUTERS
            ]
            if question.question_id == "keeps_accuracy":
                holds, text = _keeps_accuracy(comparisons, reports)
            elif question.question_id == "fastest_faster_when_told":
                holds, text = _fastest_faster(rows)
            elif question.question_id == "expensive_price_x4":
                holds, text = _price_x4(rows, data["prompts"])
            else:
                holds, text = _outage(rows)
            verdicts[evaluation_id] = holds
            texts[evaluation_id] = text
            evidence += rows
        answers.append(QuestionAnswer(
            question_id=question.question_id,
            question=question.question,
            rule=question.rule,
            holds_fresh=verdicts["final"],
            holds_test=verdicts["cp3_test"],
            answer_fresh=texts["final"],
            answer_test=texts["cp3_test"],
            evidence=evidence,
        ))
    return answers


def evaluate(
    suite: Suite,
    split: RouterSplit | None,
    evaluation_id: str,
    title: str,
    description: str,
    router: LearnedRouter,
    base: Knowledge,
    retired_ms: float,
    gemma_ratio: float,
    drift_in_world: bool,
    presets: dict[str, dict[RoutingPriority, RoutingWeights]],
    reference: ScoringReference,
    notes: list[str],
) -> tuple[ScoringFixEvaluation, list[PairedComparison], dict[str, RobustnessReport]]:
    models = router.pool_ids
    prompts = (
        complete(suite.cells, split, models) if split is not None
        else sorted(suite.items)
    )
    cells = [cell for cell in suite.cells if cell.sample_id in set(prompts)]
    world = World(cells, retired_ms)
    view = RouterView(router, suite.items, prompts)
    specs = scoring_fix_scenarios(
        models, gemma_price_ratio=gemma_ratio, drift_in_world=drift_in_world
    )
    reports = {
        "frozen": run_scenarios(
            evaluation_id, view, world, prompts, models, specs, base, notes,
            presets=presets["frozen"],
        ),
        "fixed": run_scenarios(
            evaluation_id, view, world, prompts, models, specs, base, notes,
            presets=presets["fixed"], scoring_reference=reference,
        ),
    }
    comparisons = paired_tests(
        view, world, prompts, {spec.scenario_id: spec for spec in specs}, base, presets,
        reference,
    )
    counts = Counter(cell.model_id for cell in cells)
    if any(counts[model] != len(prompts) for model in models):
        raise RuntimeError(f"{evaluation_id}: a model lacks an outcome for some prompts")
    evaluation = ScoringFixEvaluation(
        evaluation_id=evaluation_id,
        title=title,
        description=description,
        prompts=len(prompts),
        models=models,
        matrix=matrix_summary(cells, router.models),
        comparisons=comparisons,
        frozen=reports["frozen"],
        fixed=reports["fixed"],
    )
    return evaluation, comparisons, reports


def build_report() -> ScoringFixReport:
    pool = load_pool(POOL_PATH)
    router = load_router(ROUTER_MODEL_PATH, pool)
    catalog = LiveCatalogStatus.model_validate_json(CATALOG_PATH.read_text(encoding="utf-8"))
    drift = catalog_knowledge(catalog)
    suites = load_suites()
    retired_ms = retired_call_latency(suites["final"].cells)
    tuning, _ = tune_fixed_variant(router, suites["cp3"])
    reference = ScoringReference.from_estimates(router.artifact.estimates)
    presets = {
        "frozen": dict(router.artifact.weights),
        "fixed": fixed_presets(tuning),
    }
    gemma_ratio = drift.price.get("gemma-4-26b", 1.0)
    cp3, cp3_comparisons, cp3_reports = evaluate(
        suites["cp3"], RouterSplit.TEST, "cp3_test", "Original test split",
        "The 120 held-out test prompts of the 600-prompt suite, answered in late October.",
        router, Knowledge(), retired_ms, gemma_ratio, False, presets, reference,
        ["Outcomes are the stored late-October calls; every scenario rescales them."],
    )
    final, final_comparisons, final_reports = evaluate(
        suites["final"], None, "final", "Fresh prompts",
        f"The {len(suites['final'].items)} fresh prompts drawn after the router was frozen, "
        "answered on 2026-11-13 and 14, with the live catalog of 2026-11-13 applied.",
        router, drift, retired_ms, gemma_ratio, True, presets, reference,
        ["The stored calls already include the observed drift of Nov 12-13; hypothetical "
         "scenarios and the Gemma 4 26B one apply on top of the live catalog of 2026-11-13."],
    )
    questions = answer_questions({
        "cp3_test": {"comparisons": cp3_comparisons, "reports": cp3_reports,
                     "prompts": cp3.prompts},
        "final": {"comparisons": final_comparisons, "reports": final_reports,
                  "prompts": final.prompts},
    })
    weights = {
        key: {priority: value.model_dump() for priority, value in table.items()}
        for key, table in presets.items()
    }
    floor = tuning.reliability_floor
    return ScoringFixReport(
        study_id="scoring-fix",
        title="The scoring fix, tested",
        artifact_id=router.artifact.artifact_id,
        artifact_sha256=_sha256(ROUTER_MODEL_PATH),
        final_set_sha256=_sha256(FINAL_PATH),
        pool_snapshot_id=pool.snapshot_id,
        reference=reference,
        frozen_weights=weights["frozen"],
        fixed_weights=weights["fixed"],
        tuning=tuning,
        protocol=[
            "The frozen router is data/learned/cp3-router-model.json, exported on 2026-11-03, "
            "and remains the evaluated system. Nothing in it, in final-evaluation.json or in "
            "any other committed report changes.",
            "The fixed variant has the same classifier and features. It divides each model's "
            "expected cost and time by fixed references, the largest expected cost and time per "
            "task group among the frozen pool's estimates, instead of the largest among the "
            "available models, and gives reliability a small default weight.",
            f"The reliability weight and the presets were chosen on the Checkpoint 3 validation "
            f"split only, with the frozen recipe: a classifier refit on the training split, "
            f"the same weight grids, accuracy floors and tie-breaks, and the reliability grid "
            f"floored at {floor:g}. The recipe rerun with the old normalization and grid "
            f"{'reproduces' if tuning.frozen_recipe_reproduced else 'does NOT reproduce'} "
            "the frozen presets.",
            "The questions were fixed in code (FIXED_QUESTIONS) on 2026-11-26 before any result "
            "of the fixed variant was read. p-values are exact McNemar tests on the prompts "
            "where exactly one of two settings is right, Holm-adjusted together within each "
            "evaluation.",
            "'Told' is the router that learns the change, as the live catalog or call "
            "monitoring would tell it; 'old estimates' keeps its trained estimates. Both use "
            "the same presets in the same changed world, and neither is retrained.",
            "Everything is offline replay of the committed cell table (cells.jsonl); no "
            "provider is called.",
        ],
        caveats=[
            "The fresh prompts are read again here (they were used for the frozen evaluation, "
            "its robustness scenarios and the two pool studies). Nothing was tuned on them: "
            "the fixed variant's presets come from the validation split.",
            "The fixed variant is a tested recommendation, not the evaluated system: the "
            "frozen router remains the one whose held-out results were reported.",
            "The references are stored in this report, not in the router file, which stays "
            "byte-identical to the frozen export.",
            "The scenarios were chosen after the flaws were found, so they are the cases the "
            "fix was built for. They show that the fix repairs those cases; they do not show "
            "it is better in situations nobody tested.",
            "The Gemma 4 26B scenario replays the failed calls with Mercury 3's real 404 time, "
            "since no real calls to Gemma 4 26B after it went away were made.",
        ],
        questions=questions,
        evaluations=[cp3, final],
        cell_tables=[CELLS_PATH.relative_to(REPOSITORY_ROOT).as_posix()],
    )


def summarize(report: ScoringFixReport) -> list[str]:
    lines = [
        f"reference cost {report.reference.cost_usd}",
        f"reference latency {report.reference.latency_ms}",
        f"recipe reproduced: {report.tuning.frozen_recipe_reproduced}",
    ]
    for result in report.tuning.fixed_presets:
        lines.append(f"fixed {result.priority.value}: {result.weights.model_dump()} -> "
                     f"{result.validation_correct}/{report.tuning.validation_prompts}")
    for result in report.tuning.reference_only_presets:
        lines.append(f"reference only {result.priority.value}: {result.weights.model_dump()}")
    for question in report.questions:
        lines.append(f"{question.question_id}: fresh {question.holds_fresh}, "
                     f"test {question.holds_test}")
        lines.append(f"  fresh: {question.answer_fresh}")
        lines.append(f"  test: {question.answer_test}")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.parse_args(argv)
    report = build_report()
    REPORT_PATH.write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
    for line in summarize(report):
        print(line)
    print(f"wrote {REPORT_PATH.relative_to(REPOSITORY_ROOT)}")
    return 0




if __name__ == "__main__":
    raise SystemExit(main())
