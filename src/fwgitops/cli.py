"""fwctl — command line entrypoint.

  fwctl validate   # offline: check YAML against safety guardrails
  fwctl plan       # online: diff desired vs. device, print create/update plan
  fwctl apply      # online: enforce guardrails + tripwire, then apply
"""

from __future__ import annotations

import sys

import typer
from rich.console import Console
from rich.table import Table

from .applier import apply_plan
from .config import FortiGateConfig
from .fortigate import FortiGateClient
from .loader import load_desired_state, load_rules
from .planner import Plan, build_plan
from .validator import validate as run_validate

app = typer.Typer(add_completion=False, help="FortiGate GitOps automation.")
console = Console()


def _validate_or_exit() -> None:
    state = load_desired_state()
    rules = load_rules()
    errors = run_validate(state, rules)
    if errors:
        console.print("[bold red]Validation failed:[/bold red]")
        for e in errors:
            console.print(f"  - {e}")
        raise typer.Exit(code=1)
    console.print("[bold green]Validation passed.[/bold green]")


@app.command()
def validate() -> None:
    """Check the desired-state YAML against config/policy_rules.yaml."""
    _validate_or_exit()


def _render_plan(plan: Plan) -> None:
    table = Table(title="FortiGate change plan")
    table.add_column("Action")
    table.add_column("Kind")
    table.add_column("Name")
    table.add_column("Details")
    for item in plan.items:
        color = {"create": "green", "update": "yellow", "noop": "dim"}[item.action]
        details = "; ".join(item.changes) if item.changes else "-"
        table.add_row(
            f"[{color}]{item.action}[/{color}]", item.kind, item.name, details
        )
    console.print(table)
    console.print(f"[bold]Plan: {plan.summary()}[/bold]")


@app.command()
def plan() -> None:
    """Show the create/update plan against the live device (no changes made)."""
    _validate_or_exit()
    state = load_desired_state()
    client = FortiGateClient(FortiGateConfig.from_env())
    _render_plan(build_plan(state, client))


@app.command()
def apply(
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the interactive confirmation."
    ),
) -> None:
    """Apply the plan to the live device after guardrails + tripwire pass."""
    _validate_or_exit()
    state = load_desired_state()
    rules = load_rules()
    client = FortiGateClient(FortiGateConfig.from_env())
    plan_obj = build_plan(state, client)
    _render_plan(plan_obj)

    changed = plan_obj.changed
    if not changed:
        console.print("Nothing to apply.")
        return

    tripwire = rules.get("max_changes_per_apply", 10)
    if len(changed) > tripwire:
        console.print(
            f"[bold red]Refusing to apply {len(changed)} changes "
            f"(max_changes_per_apply={tripwire}).[/bold red]"
        )
        raise typer.Exit(code=2)

    if not yes:
        confirm = typer.confirm(f"Apply {len(changed)} change(s)?")
        if not confirm:
            console.print("Aborted.")
            raise typer.Exit(code=0)

    for line in apply_plan(plan_obj, client):
        console.print(line)
        if line.startswith("[ERROR]"):
            sys.exit(1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
