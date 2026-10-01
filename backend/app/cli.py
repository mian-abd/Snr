from __future__ import annotations

import argparse
import asyncio

import uvicorn

from app.config import get_settings
from app.domain.models import BenchmarkMode
from app.state import build_services


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Adaptive LLM Router utilities")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight", help="Validate the pinned model registry against OpenRouter")
    subparsers.add_parser("pilot", help="Run the fixed two-question pilot")
    subparsers.add_parser("full", help="Run the fixed 12-question benchmark")
    resume = subparsers.add_parser("resume", help="Resume a specific benchmark run")
    resume.add_argument("run_id")
    resume.add_argument("--mode", choices=["pilot", "full"], default="full")
    sanitize = subparsers.add_parser("sanitize", help="Export a completed run as demo evidence")
    sanitize.add_argument("run_id")
    subparsers.add_parser("serve", help="Serve the production API and built frontend")
    return parser


async def _execute(args: argparse.Namespace) -> None:
    settings = get_settings()
    services = build_services(settings)
    if args.command == "preflight":
        if not settings.credential_configured:
            raise SystemExit("A replacement OPENROUTER_API_KEY is required in backend/.env")
        assert settings.openrouter_api_key is not None
        await services.registry.validate_live_catalog(
            settings.openrouter_api_key.get_secret_value()
        )
        print("Preflight passed for both pinned models.")
        return
    if args.command == "sanitize":
        if services.benchmark_runner is None:
            raise SystemExit("OPENROUTER_API_KEY must be configured to initialize the runner")
        destination = services.benchmark_runner.sanitize_run(args.run_id)
        print(f"Sanitized evidence written to {destination}")
        return
    if services.benchmark_runner is None:
        raise SystemExit("A replacement OPENROUTER_API_KEY is required in backend/.env")
    if args.command == "resume":
        view = await services.benchmark_runner.run(BenchmarkMode(args.mode), args.run_id)
    else:
        mode = BenchmarkMode.PILOT if args.command == "pilot" else BenchmarkMode.FULL
        view = await services.benchmark_runner.run(mode)
    print(view.model_dump_json(indent=2))


def main() -> None:
    args = _parser().parse_args()
    if args.command == "serve":
        uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=False)
        return
    asyncio.run(_execute(args))


if __name__ == "__main__":
    main()
