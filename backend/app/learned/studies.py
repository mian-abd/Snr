"""Pool studies: the frozen router's pool widened with more models, and a router refit for each.

This module only names things (no training code), so the server can load the studies' routers
at startup without importing the training stack. ``app.learned.pool_study`` builds them.

An *added pool* is a dated registry of extra models with the run folders that answered the
same 900 prompts as the Checkpoint 3 pool. A *study* adds one or more of them to the pool, refits
the Checkpoint 3 recipe unchanged, and evaluates the new router next to the frozen one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.config import REPOSITORY_ROOT

LEARNED_DIR = REPOSITORY_ROOT / "data" / "learned"
REGISTRY_DIR = REPOSITORY_ROOT / "data" / "registry"


@dataclass(frozen=True)
class AddedPool:
    name: str
    label: str  # one model, as the site tags it
    plural: str  # several, in prose
    registry_file: str  # under data/registry
    run_ids: dict[str, str]  # suite ("cp3" or "final") -> run folder under data/local/cp3
    answered_on: str
    # Why a listed model did not answer every prompt; {scored} and {total} are filled in.
    stopped: dict[str, str] = field(default_factory=dict)

    @property
    def registry(self) -> Path:
        return REGISTRY_DIR / self.registry_file

    @property
    def cells_path(self) -> Path:
        return LEARNED_DIR / f"{self.name}-cells.jsonl"


ADDED_POOLS: dict[str, AddedPool] = {
    "flagship": AddedPool(
        name="flagship",
        label="Flagship",
        plural="flagships",
        registry_file="flagship-pool-2026-11-14.json",
        run_ids={"cp3": "flagship-cp3", "final": "flagship-final"},
        answered_on="2026-11-14",
        stopped={
            "grok-4.7": (
                "Stopped on 2026-11-14 after {scored} of {total} prompts. Its reasoning ignored "
                "the 4,096-token answer limit on knowledge questions (one answer ran to 35,234 "
                "tokens and ten minutes), so finishing would have taken the flagship runs past "
                "their $25 budget."
            ),
        },
    ),
    "budget": AddedPool(
        name="budget",
        label="Budget",
        plural="budget models",
        registry_file="budget-pool-2026-11-20.json",
        run_ids={"cp3": "budget-cp3", "final": "budget-final"},
        answered_on="2026-11-21",
        stopped={
            "nemotron-3.5-lightning-free": (
                "Smoke-tested on 8 prompts, then not run in full ({scored} of {total} prompts): "
                "the account's 1,000 free requests a day covered one free model on 2026-11-21, "
                "and NVIDIA is already in the pool."
            ),
            # ERNIE 5.5 Flash stopped on 2026-11-21 at 884 of 900 prompts when the free daily
            # quota ran out. As committed before the wide study was first built, its 16 unsent
            # fresh prompts ran on 2026-11-24 and the study was rebuilt with it, whatever the
            # result.
        },
    ),
}


@dataclass(frozen=True)
class StudySpec:
    study_id: str
    title: str
    question: str  # {added} is the number of added models that answered every prompt
    pools: tuple[str, ...]
    # Earlier studies whose routers join as baselines, as "<study>_router:<priority>".
    baseline_studies: tuple[str, ...]
    # Fixed in code before the study's results were read: (strategy, baseline, question).
    comparisons: tuple[tuple[str, str, str], ...]
    reuse_note: str

    @property
    def report_path(self) -> Path:
        return LEARNED_DIR / f"{self.study_id}-study.json"

    @property
    def router_path(self) -> Path:
        return LEARNED_DIR / f"{self.study_id}-router-model.json"

    @property
    def added(self) -> list[AddedPool]:
        return [ADDED_POOLS[name] for name in self.pools]


TOP_ADDED = "fixed_top_added"

STUDIES: dict[str, StudySpec] = {
    # Fixed on 2026-11-14 before any flagship result was read.
    "flagship": StudySpec(
        study_id="flagship",
        title="With flagship models",
        question="Does adding {added} flagship models to the pool pay off?",
        pools=("flagship",),
        baseline_studies=(),
        comparisons=(
            ("learned:quality", "previous_router:quality",
             "Does the best-quality setting get more right with the flagships in the pool?"),
            ("learned:quality", TOP_ADDED,
             "Is the best-quality setting as accurate as always using the strongest flagship, "
             "for less?"),
            ("learned:cost", "previous_router:cost",
             "Does adding the flagships change the lowest-cost setting?"),
            ("learned:latency", "previous_router:latency",
             "Does adding the flagships change the fastest setting?"),
            ("learned:balanced", "previous_router:balanced",
             "Does the balanced setting do better with the flagships in the pool?"),
            ("learned:quality", "model_task_prior:quality",
             "With the flagships, do the prompt features add accuracy beyond per-task averages?"),
        ),
        reuse_note=(
            "The fresh prompts were already used once, to evaluate the frozen router. Nothing in "
            "this extension was chosen on them; they are read once more here."
        ),
    ),
    # Fixed on 2026-11-21 while the budget models were still running, before any of their
    # results were read.
    "wide": StudySpec(
        study_id="wide",
        title="With every model",
        question="Does a wider pool, with {added} flagship and budget models added, pay off?",
        pools=("flagship", "budget"),
        baseline_studies=("flagship",),
        comparisons=(
            ("learned:quality", "previous_router:quality",
             "Does the best-quality setting get more right with the wider pool?"),
            ("learned:cost", "previous_router:cost",
             "Does the wider pool change the lowest-cost setting?"),
            ("learned:latency", "previous_router:latency",
             "Does the wider pool change the fastest setting?"),
            ("learned:balanced", "previous_router:balanced",
             "Does the balanced setting do better with the wider pool?"),
            ("learned:quality", "flagship_router:quality",
             "Do the budget models add anything at best quality beyond the flagships?"),
            ("learned:cost", "flagship_router:cost",
             "Do the budget models help the lowest-cost setting beyond the flagships?"),
            ("learned:quality", TOP_ADDED,
             "Is the best-quality setting as accurate as always using the strongest added model, "
             "for less?"),
            ("learned:quality", "model_task_prior:quality",
             "With the wider pool, do the prompt features add accuracy beyond per-task averages?"),
        ),
        reuse_note=(
            "The fresh prompts were already read twice, for the frozen router and the flagship "
            "study. The budget models were chosen from the live catalog by price before any of "
            "their results were read, and nothing here was tuned on the fresh prompts."
        ),
    ),
}

# Which study's router serves each pool the site offers (besides the frozen "standard" one).
POOL_STUDY = {"flagships": "flagship", "wide": "wide"}
