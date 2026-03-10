"""
feedback_cli.py - Command-line interface for the PCM Feedback Loop system.

Usage examples
--------------
Add a correction:
    python feedback_cli.py --add --section 2.3 --type term \
        --original "장" --corrected "체" --notes "대수학 문맥"

Show dashboard summary:
    python feedback_cli.py --dashboard

List all stored feedback entries:
    python feedback_cli.py --list

Show what would be injected into the translator prompt for a section:
    python feedback_cli.py --inject --section 2.3
"""

import argparse
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so the src package is importable
# regardless of how the script is invoked.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.pcm.core.feedback_loop import (
    FeedbackDB,
    FeedbackEntry,
    FeedbackInjector,
    ImpactScorer,
    VALID_FEEDBACK_TYPES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_db() -> FeedbackDB:
    return FeedbackDB()


def cmd_add(args: argparse.Namespace, db: FeedbackDB) -> int:
    """Add a new feedback correction to the database."""
    if not args.section:
        print("ERROR: --section is required with --add", file=sys.stderr)
        return 1
    if not args.type:
        print("ERROR: --type is required with --add", file=sys.stderr)
        return 1
    if args.type not in VALID_FEEDBACK_TYPES:
        print(
            f"ERROR: --type must be one of {VALID_FEEDBACK_TYPES}",
            file=sys.stderr,
        )
        return 1
    if not args.original:
        print("ERROR: --original is required with --add", file=sys.stderr)
        return 1
    if not args.corrected:
        print("ERROR: --corrected is required with --add", file=sys.stderr)
        return 1

    entry = FeedbackEntry(
        feedback_id=db.next_id(),
        section_id=args.section,
        feedback_type=args.type,
        original=args.original,
        corrected=args.corrected,
        notes=args.notes or "",
    )

    # Score immediately so the stored record carries its impact value
    scorer = ImpactScorer()
    entry.impact_score = scorer.score(entry)

    db.add(entry)

    print(f"Saved feedback [{entry.feedback_id}]")
    print(f"  Section  : {entry.section_id}")
    print(f"  Type     : {entry.feedback_type}")
    print(f"  Original : {entry.original}")
    print(f"  Corrected: {entry.corrected}")
    if entry.notes:
        print(f"  Notes    : {entry.notes}")
    print(f"  Impact   : {entry.impact_score:.3f}")
    return 0


def cmd_dashboard(db: FeedbackDB) -> int:
    """Print a statistics dashboard for all stored feedback."""
    stats = db.get_stats()

    print("=" * 50)
    print("  PCM Feedback Dashboard")
    print("=" * 50)
    print(f"  Total corrections : {stats['total_corrections']}")
    print()

    print("  By type:")
    if stats["by_type"]:
        for ftype, count in sorted(stats["by_type"].items(), key=lambda x: -x[1]):
            bar = "#" * count
            print(f"    {ftype:<12} {count:>4}  {bar}")
    else:
        print("    (none)")
    print()

    print("  Most frequent corrections (top 10):")
    if stats["most_frequent"]:
        for i, (pair, count) in enumerate(stats["most_frequent"], 1):
            print(f"    {i:>2}. [{count}x]  {pair}")
    else:
        print("    (none)")
    print("=" * 50)
    return 0


def cmd_list(db: FeedbackDB) -> int:
    """Print all stored feedback entries."""
    entries = db.all()
    if not entries:
        print("No feedback entries found.")
        return 0

    print(f"{'ID':<10} {'Section':<10} {'Type':<12} {'Original':<20} {'Corrected':<20} {'Impact'}")
    print("-" * 90)
    for e in entries:
        orig = (e.original[:18] + "..") if len(e.original) > 20 else e.original
        corr = (e.corrected[:18] + "..") if len(e.corrected) > 20 else e.corrected
        print(
            f"{e.feedback_id:<10} {e.section_id:<10} {e.feedback_type:<12} "
            f"{orig:<20} {corr:<20} {e.impact_score:.3f}"
        )
    print(f"\nTotal: {len(entries)} entries")
    return 0


def cmd_inject(args: argparse.Namespace, db: FeedbackDB) -> int:
    """Show what would be injected into the translator prompt for a section."""
    if not args.section:
        print("ERROR: --section is required with --inject", file=sys.stderr)
        return 1

    injector = FeedbackInjector(db=db)
    top_k = args.top_k if args.top_k else 5
    result = injector.inject_to_translator_prompt(
        section_id=args.section,
        top_k=top_k,
    )
    print(result)
    return 0


# ---------------------------------------------------------------------------
# CLI definition
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="feedback_cli.py",
        description="PCM Translation Feedback Loop CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # Mutually exclusive top-level commands
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--add",
        action="store_true",
        help="Add a new feedback correction",
    )
    mode.add_argument(
        "--dashboard",
        action="store_true",
        help="Show feedback statistics dashboard",
    )
    mode.add_argument(
        "--list",
        action="store_true",
        help="List all stored feedback entries",
    )
    mode.add_argument(
        "--inject",
        action="store_true",
        help="Show the prompt injection for a given section",
    )

    # Arguments used by --add and --inject
    parser.add_argument("--section", metavar="SECTION_ID", help="Section identifier (e.g. 2.3)")
    parser.add_argument(
        "--type",
        metavar="TYPE",
        help=f"Feedback type: {', '.join(VALID_FEEDBACK_TYPES)}",
    )
    parser.add_argument("--original", metavar="TEXT", help="Original (wrong) translation")
    parser.add_argument("--corrected", metavar="TEXT", help="Corrected translation")
    parser.add_argument("--notes", metavar="TEXT", help="Optional notes or context")
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        metavar="N",
        help="Number of examples to inject (default: 5)",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    db = _make_db()

    if args.add:
        return cmd_add(args, db)
    elif args.dashboard:
        return cmd_dashboard(db)
    elif args.list:
        return cmd_list(db)
    elif args.inject:
        return cmd_inject(args, db)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
