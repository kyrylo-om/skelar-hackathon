"""Django management command to execute the scenario evaluation suite."""

import sys

from django.core.management.base import BaseCommand

from evals.reports import format_summary, format_table, write_reports
from evals.runner import load_scenarios, run_all


class Command(BaseCommand):
    help = "Run the scenario evaluation suite through the real orchestrator."

    def add_arguments(self, parser):
        parser.add_argument(
            "--mode",
            choices=["mock", "live"],
            default="mock",
            help="Execution mode: mock (deterministic stand-in) or live (DeepSeek LLM)",
        )
        parser.add_argument("--tenant", type=str, help="Filter scenarios by tenant")
        parser.add_argument("--tag", type=str, help="Filter scenarios by tag")
        parser.add_argument(
            "--repeat", type=int, default=1, help="Number of repetitions per scenario"
        )
        parser.add_argument(
            "--out", type=str, default="reports", help="Directory where reports are written"
        )
        parser.add_argument(
            "--max-llm-calls", type=int, default=300, help="Maximum allowed LLM calls in live mode"
        )
        parser.add_argument(
            "--yes", action="store_true", help="Skip confirmation prompt before live mode"
        )

    def handle(self, *args, **options):
        mode = options["mode"]
        tenant = options.get("tenant")
        tag = options.get("tag")
        repeat = options["repeat"]
        out_dir = options["out"]

        scenarios = load_scenarios(tag=tag, tenant=tenant)
        if not scenarios:
            self.stdout.write(self.style.WARNING("No scenarios matched the given filters."))
            return

        self.stdout.write(
            f"Loaded {len(scenarios)} scenarios (mode={mode}, repeat={repeat}, tag={tag or 'all'})."
        )

        if mode == "live" and not options.get("yes"):
            estimated_calls = len(scenarios) * repeat * 4
            self.stdout.write(
                f"ATTENTION: Live mode will use DeepSeek API. Estimated calls: ~{estimated_calls}."
            )
            confirm = input("Proceed? [y/N]: ").strip().lower()
            if confirm != "y":
                self.stdout.write("Aborted.")
                return

        summary, results = run_all(scenarios, mode=mode, repeat=repeat)

        # Print table and summary
        self.stdout.write("\n" + format_table(results))
        self.stdout.write("\n" + format_summary(summary) + "\n")

        # Save reports
        json_path, md_path = write_reports(summary, results, out_dir=out_dir)
        self.stdout.write(self.style.SUCCESS(f"Reports saved to {md_path.parent}"))

        # Exit code 1 if any scenario failed
        if summary["failed"] > 0:
            sys.exit(1)
