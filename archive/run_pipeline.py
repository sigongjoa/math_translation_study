#!/usr/bin/env python3
"""
MasterPipeline CLI entry point.

Usage:
  python run_pipeline.py run --pdf path/to/book.pdf --pages 12-15
  python run_pipeline.py run --pdf path/to/book.pdf --pages 12-15 --resume job_20260310_001
  python run_pipeline.py status --job job_20260310_001
  python run_pipeline.py logs --job job_20260310_001 [--level ERROR] [--stage 3]
  python run_pipeline.py list
  python run_pipeline.py demo
"""

import argparse
import json
import sys


def cmd_run(args):
    from src.pcm.pipeline import MasterPipeline

    # Parse --pages "12-15" into start_page, end_page
    try:
        parts = args.pages.split("-")
        start_page = int(parts[0])
        end_page = int(parts[1])
    except (IndexError, ValueError):
        print(f"[ERROR] --pages must be in format START-END, got: {args.pages}")
        sys.exit(1)

    pipeline = MasterPipeline(db_path=args.db)
    job_id = pipeline.run(
        pdf_path=args.pdf,
        start_page=start_page,
        end_page=end_page,
        job_id=args.resume,
    )
    print(f"\nJob completed: {job_id}")
    pipeline.status(job_id)


def cmd_status(args):
    from src.pcm.pipeline import MasterPipeline

    pipeline = MasterPipeline(db_path=args.db)
    pipeline.status(args.job)


def cmd_logs(args):
    from src.pcm.pipeline import PipelineDB

    db = PipelineDB(db_path=args.db)
    logs = db.get_logs(
        job_id=args.job,
        level=args.level,
        stage_num=args.stage,
    )
    if not logs:
        print("No logs found for the given filters.")
        return

    for entry in logs:
        details_str = ""
        if entry.get("details") and entry["details"] != "{}":
            try:
                d = json.loads(entry["details"])
                # Truncate traceback for readability
                if "traceback" in d:
                    d["traceback"] = d["traceback"][:300] + "..."
                details_str = f"  {json.dumps(d, ensure_ascii=False)}"
            except (json.JSONDecodeError, TypeError):
                details_str = f"  {entry['details']}"

        stage_tag = f"[S{entry['stage_num']}]" if entry.get("stage_num") else "   "
        print(
            f"{entry['timestamp'][:19]} {stage_tag} "
            f"[{entry['level']:<7}] [{entry['agent_name']}] "
            f"{entry['message']}"
        )
        if details_str:
            print(details_str)


def cmd_list(args):
    from src.pcm.pipeline import MasterPipeline

    pipeline = MasterPipeline(db_path=args.db)
    pipeline.list_jobs()


def cmd_demo(args):
    from src.pcm.pipeline import MasterPipeline

    print("=" * 60)
    print("DEMO MODE — running with synthetic math sections")
    print("=" * 60)

    synthetic_sections = [
        {
            "section_id": "1.1",
            "text": (
                "A group is a set G together with a binary operation "
                "satisfying associativity, identity, and inverses."
            ),
        },
        {
            "section_id": "1.2",
            "text": (
                "A ring is an abelian group under addition, with an "
                "associative multiplication that distributes over addition."
            ),
        },
        {
            "section_id": "2.1",
            "text": (
                "A topological space is a set X with a collection of open "
                "sets satisfying certain axioms."
            ),
        },
    ]

    pipeline = MasterPipeline(db_path=args.db)
    job_id = pipeline.run(
        pdf_path="demo://synthetic",
        start_page=0,
        end_page=0,
        sections_override=synthetic_sections,
    )

    print(f"\nDemo job completed: {job_id}")
    pipeline.status(job_id)

    # Show a sample of the logs
    print("\n--- Recent logs (last 20) ---")
    from src.pcm.pipeline import PipelineDB

    db = PipelineDB(db_path=args.db)
    logs = db.get_logs(job_id)
    for entry in logs[-20:]:
        stage_tag = f"[S{entry['stage_num']}]" if entry.get("stage_num") else "   "
        print(
            f"{entry['timestamp'][11:19]} {stage_tag} "
            f"[{entry['level']:<7}] {entry['message']}"
        )


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="MasterPipeline CLI for PCM translation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--db",
        default="pipeline.db",
        metavar="DB_PATH",
        help="Path to the SQLite database (default: pipeline.db)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = sub.add_parser("run", help="Run a new pipeline job")
    p_run.add_argument("--pdf", required=True, help="Path to source PDF")
    p_run.add_argument(
        "--pages",
        required=True,
        metavar="START-END",
        help="Page range, e.g. 12-15",
    )
    p_run.add_argument(
        "--resume",
        metavar="JOB_ID",
        default=None,
        help="Resume an existing job by ID",
    )

    # status
    p_status = sub.add_parser("status", help="Show job status tree")
    p_status.add_argument("--job", required=True, metavar="JOB_ID")

    # logs
    p_logs = sub.add_parser("logs", help="Show agent logs for a job")
    p_logs.add_argument("--job", required=True, metavar="JOB_ID")
    p_logs.add_argument(
        "--level",
        choices=["INFO", "WARNING", "ERROR"],
        default=None,
        help="Filter by log level",
    )
    p_logs.add_argument(
        "--stage",
        type=int,
        default=None,
        metavar="STAGE_NUM",
        help="Filter by stage number (1-5)",
    )

    # list
    sub.add_parser("list", help="List all jobs")

    # demo
    sub.add_parser("demo", help="Run demo with synthetic sections (no PDF needed)")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    dispatch = {
        "run": cmd_run,
        "status": cmd_status,
        "logs": cmd_logs,
        "list": cmd_list,
        "demo": cmd_demo,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
