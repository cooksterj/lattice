"""
Command-line interface for Lattice run history.

Provides commands to list, view, and delete run records.
"""

import argparse
import json
import sys

from lattice.observability.history import SQLiteRunHistoryStore


def get_store(db_path: str | None = None) -> SQLiteRunHistoryStore:
    """
    Get a history store instance.

    Parameters
    ----------
    db_path : str or None
        Path to the database file. Defaults to 'lattice_runs.db'.

    Returns
    -------
    SQLiteRunHistoryStore
        The history store instance.
    """
    path = db_path or "lattice_runs.db"
    return SQLiteRunHistoryStore(path)


def cmd_list(args: argparse.Namespace) -> int:
    """List recent runs."""
    store = get_store(args.db)
    runs = store.list_runs(limit=args.limit, status=args.status)

    if not runs:
        print("No runs found.")
        return 0

    # Print header
    print(f"{'Run ID':<10} {'Started':<20} {'Status':<10} {'Assets':<10} {'Duration':<12}")
    print("-" * 65)

    for run in runs:
        started = run.started_at.strftime("%Y-%m-%d %H:%M:%S")
        assets = f"{run.completed_count}/{run.total_assets}"
        duration = f"{run.duration_ms:.1f}ms"
        print(f"{run.run_id:<10} {started:<20} {run.status:<10} {assets:<10} {duration:<12}")

    return 0


def cmd_show(args: argparse.Namespace) -> int:
    """Show details of a specific run."""
    store = get_store(args.db)
    record = store.get(args.run_id)

    if record is None:
        print(f"Run '{args.run_id}' not found.")
        return 1

    print(f"Run ID:      {record.run_id}")
    print(f"Status:      {record.status}")
    print(f"Started:     {record.started_at.isoformat()}")
    print(f"Completed:   {record.completed_at.isoformat()}")
    print(f"Duration:    {record.duration_ms:.2f}ms")
    print(f"Assets:      {record.completed_count}/{record.total_assets} completed")
    if record.failed_count > 0:
        print(f"Failed:      {record.failed_count}")
    if record.target:
        print(f"Target:      {record.target}")
    if record.partition_key:
        print(f"Partition:   {record.partition_key}")

    # Show asset results
    if args.assets or args.all:
        print("\n--- Asset Results ---")
        asset_results = json.loads(record.asset_results_json)
        status_icons = {"completed": "✓", "failed": "✗"}
        for ar in asset_results:
            status_icon = status_icons.get(ar["status"], "○")
            duration = f"{ar['duration_ms']:.1f}ms" if ar["duration_ms"] else "-"
            print(f"  {status_icon} {ar['key']:<30} {ar['status']:<10} {duration}")
            if ar.get("error"):
                print(f"      Error: {ar['error']}")

    # Show logs
    if args.logs or args.all:
        print("\n--- Logs ---")
        logs = json.loads(record.logs_json)
        if not logs:
            print("  (no logs captured)")
        for log in logs:
            asset_str = f"[{log['asset_key']}]" if log["asset_key"] else ""
            print(f"  {log['level']:<8} {asset_str} {log['message']}")

    # Show check results
    if args.checks or args.all:
        print("\n--- Check Results ---")
        checks = json.loads(record.check_results_json)
        if not checks:
            print("  (no checks run)")
        for check in checks:
            status_icon = "✓" if check["passed"] else "✗"
            duration = f"{check['duration_ms']:.1f}ms" if check["duration_ms"] else "-"
            check_name = check["check_name"]
            asset_key = check["asset_key"]
            print(f"  {status_icon} {check_name:<25} on {asset_key:<20} {duration}")
            if check.get("error"):
                print(f"      Error: {check['error']}")

    # Show lineage
    if args.lineage or args.all:
        print("\n--- Lineage ---")
        lineage = json.loads(record.lineage_json)
        if not lineage:
            print("  (no lineage events)")
        for event in lineage:
            source = f" (from {event['source_asset']})" if event["source_asset"] else ""
            print(f"  {event['event_type']:<6} {event['asset_key']}{source}")

    return 0


def cmd_delete(args: argparse.Namespace) -> int:
    """Delete a run record."""
    store = get_store(args.db)

    if store.delete(args.run_id):
        print(f"Deleted run '{args.run_id}'.")
        return 0
    else:
        print(f"Run '{args.run_id}' not found.")
        return 1


def cmd_clear(args: argparse.Namespace) -> int:
    """Clear all run records."""
    store = get_store(args.db)

    if not args.force:
        count = store.count()
        if count == 0:
            print("No runs to delete.")
            return 0
        response = input(f"Delete all {count} run records? [y/N] ")
        if response.lower() != "y":
            print("Aborted.")
            return 1

    deleted = store.clear()
    print(f"Deleted {deleted} run records.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """
    Main entry point for the CLI.

    Parameters
    ----------
    argv : list of str or None
        Command-line arguments. Defaults to sys.argv[1:].

    Returns
    -------
    int
        Exit code (0 for success, non-zero for errors).
    """
    parser = argparse.ArgumentParser(
        prog="lattice",
        description="Lattice run history CLI",
    )
    parser.add_argument(
        "--db",
        type=str,
        default=None,
        help="Path to SQLite database (default: lattice_runs.db)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # list command
    list_parser = subparsers.add_parser("list", help="List recent runs")
    list_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum number of runs to show (default: 20)",
    )
    list_parser.add_argument(
        "--status",
        type=str,
        choices=["completed", "failed"],
        default=None,
        help="Filter by status",
    )
    list_parser.set_defaults(func=cmd_list)

    # show command
    show_parser = subparsers.add_parser("show", help="Show run details")
    show_parser.add_argument("run_id", help="Run ID to show")
    show_parser.add_argument(
        "--logs",
        action="store_true",
        help="Include captured logs",
    )
    show_parser.add_argument(
        "--checks",
        action="store_true",
        help="Include check results",
    )
    show_parser.add_argument(
        "--lineage",
        action="store_true",
        help="Include lineage events",
    )
    show_parser.add_argument(
        "--assets",
        action="store_true",
        help="Include asset results",
    )
    show_parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Include all details (logs, checks, lineage, assets)",
    )
    show_parser.set_defaults(func=cmd_show)

    # delete command
    delete_parser = subparsers.add_parser("delete", help="Delete a run record")
    delete_parser.add_argument("run_id", help="Run ID to delete")
    delete_parser.set_defaults(func=cmd_delete)

    # clear command
    clear_parser = subparsers.add_parser("clear", help="Clear all run records")
    clear_parser.add_argument(
        "--force",
        "-f",
        action="store_true",
        help="Skip confirmation prompt",
    )
    clear_parser.set_defaults(func=cmd_clear)

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
