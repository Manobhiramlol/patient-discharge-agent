"""CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from agent.loop import run_agent

load_dotenv()
console = Console()


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def cmd_run(args: argparse.Namespace) -> int:
    root = _repo_root()
    data_root = Path(args.data) if args.data else root / "data"
    output_root = Path(args.output) if args.output else root / "outputs"

    result = run_agent(
        patient_id=args.patient,
        data_root=data_root,
        output_root=output_root,
        max_steps=args.max_steps,
    )
    console.print(f"[green]Done[/green] {args.patient} -> {result['output_dir']}")
    if result.get("flags"):
        console.print(f"  Flags: {', '.join(result['flags'])}")
    return 0


def cmd_run_all(args: argparse.Namespace) -> int:
    root = _repo_root()
    data_root = Path(args.data) if args.data else root / "data"
    output_root = Path(args.output) if args.output else root / "outputs"
    patients_dir = data_root / "patients"

    if not patients_dir.is_dir():
        console.print(f"[red]No patients at {patients_dir}[/red]")
        return 1

    patient_ids = sorted(
        d.name for d in patients_dir.iterdir() if d.is_dir() and not d.name.startswith(".")
    )
    if not patient_ids:
        console.print("[red]No patient folders found[/red]")
        return 1

    results = []
    for pid in patient_ids:
        console.print(f"Processing [bold]{pid}[/bold]...")
        try:
            r = run_agent(pid, data_root, output_root, max_steps=args.max_steps)
            results.append(r)
        except Exception as e:  # noqa: BLE001
            console.print(f"[red]Failed {pid}: {e}[/red]")
            results.append({"patient_id": pid, "error": str(e)})

    summary_path = output_root / "batch_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    console.print(f"\n[green]Batch complete[/green] - {len(results)} patients -> {summary_path}")
    return 0


def cmd_list_patients(args: argparse.Namespace) -> int:
    root = _repo_root()
    data_root = Path(args.data) if args.data else root / "data"
    patients_dir = data_root / "patients"
    table = Table(title="Patients")
    table.add_column("ID")
    table.add_column("PDFs")
    if not patients_dir.is_dir():
        console.print("[yellow]No data/patients — run scripts/generate_synthetic_data.py[/yellow]")
        return 0
    for d in sorted(patients_dir.iterdir()):
        if d.is_dir():
            pdfs = list(d.glob("*.pdf"))
            table.add_row(d.name, str(len(pdfs)))
    console.print(table)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Discharge summary agent")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Run agent for one patient")
    p_run.add_argument("--patient", required=True)
    p_run.add_argument("--data", default=None)
    p_run.add_argument("--output", default=None)
    p_run.add_argument("--max-steps", type=int, default=None)
    p_run.set_defaults(func=cmd_run)

    p_all = sub.add_parser("run-all", help="Run agent for all patients")
    p_all.add_argument("--data", default=None)
    p_all.add_argument("--output", default=None)
    p_all.add_argument("--max-steps", type=int, default=None)
    p_all.set_defaults(func=cmd_run_all)

    p_list = sub.add_parser("list", help="List patients")
    p_list.add_argument("--data", default=None)
    p_list.set_defaults(func=cmd_list_patients)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
