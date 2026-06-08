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
from .route_selector import load_devices, select_targets
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


@app.command()
def routes() -> None:
    """Show the routing table of each firewall in config/devices.yaml.

    In dry-run mode these come from devices.yaml; with a live device they would
    come from GET /api/v2/monitor/router/ipv4.
    """
    devices = load_devices()
    if not devices:
        console.print(
            "[bold red]No devices found in config/devices.yaml.[/bold red]"
        )
        raise typer.Exit(code=1)

    for dev in devices:
        title = f"{dev.name}"
        if dev.host:
            title += f"  ({dev.host})"
        table = Table(title=title)
        table.add_column("Destination")
        table.add_column("Interface")
        table.add_column("Type")
        table.add_column("Gateway")
        for r in sorted(dev.routes, key=lambda x: x.prefixlen, reverse=True):
            kind = (
                "[cyan]connected[/cyan]"
                if r.type == "connected"
                else ("[dim]default[/dim]" if r.is_default else r.type)
            )
            table.add_row(r.dst, r.interface, kind, r.gateway or "-")
        console.print(table)
        console.print()


@app.command()
def select() -> None:
    """Pick the target firewall for each policy from its routing path.

    Uses config/devices.yaml. In dry-run mode the routing tables defined there
    are used; otherwise the live device's route lookup would be queried.
    """
    state = load_desired_state()
    devices = load_devices()
    if not devices:
        console.print(
            "[bold red]No devices found in config/devices.yaml.[/bold red]"
        )
        raise typer.Exit(code=1)

    addr_index = {a.name: a for a in state.addresses}

    for policy in state.policies:
        selection = select_targets(policy, addr_index, devices)
        chosen = selection.chosen

        table = Table(title=f"Policy '{policy.name}'  ({_endpoints(policy)})")
        table.add_column("Firewall")
        table.add_column("src route")
        table.add_column("dst route")
        table.add_column("Verdict")
        for m in selection.matches:
            picked = chosen is not None and m.device == chosen.device
            verdict = (
                "[bold green]TARGET[/bold green]"
                if picked
                else ("[yellow]transit[/yellow]" if m.is_transit else "[dim]skip[/dim]")
            )
            table.add_row(
                m.device,
                _route_cell(m.src_route),
                _route_cell(m.dst_route),
                f"{verdict}  [dim]{m.reason}[/dim]",
            )
        console.print(table)
        if chosen is None:
            console.print(
                "  [bold red]No firewall is on the path for this policy.[/bold red]"
            )
        else:
            ci = chosen.src_route.interface  # type: ignore[union-attr]
            co = chosen.dst_route.interface  # type: ignore[union-attr]
            console.print(
                f"  -> target: [bold green]{chosen.device}[/bold green] "
                f"(srcintf={ci}, dstintf={co})"
            )
        console.print()


def _endpoints(policy) -> str:
    return f"{','.join(policy.srcaddr)} -> {','.join(policy.dstaddr)}"


def _route_cell(route) -> str:
    if route is None:
        return "[red]none[/red]"
    return f"{route.dst} via {route.interface} ({route.type})"


def main() -> None:
    app()


if __name__ == "__main__":
    main()
