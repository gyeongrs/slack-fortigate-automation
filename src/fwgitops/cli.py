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

from .address_resolver import resolve_one
from .expiry import load_expiry_config, policies_due_for_alert
from .loader import load_desired_state, load_rules, load_shared_services
from .models import Address, Policy
from .multi_device import apply_all_devices, combined_plan
from .planner import Plan
from .route_selector import load_devices, select_targets
from .router_monitor import (
    load_devices_live,
    load_route_probes_from_repo,
    sync_routes_file,
)
from .validator import validate as run_validate

app = typer.Typer(add_completion=False, help="FortiGate GitOps automation.")
routes_app = typer.Typer(help="Routing table reference and live lookup.")
app.add_typer(routes_app, name="routes")
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


def _render_plan(plan: Plan, title: str = "FortiGate change plan") -> None:
    table = Table(title=title)
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
    """Show the create/update plan against inventory device(s) (no changes made)."""
    _validate_or_exit()
    state = load_desired_state()
    plans, devices = combined_plan(state)
    if devices:
        console.print(
            f"[bold]Shared services ({len(state.services)}) apply to all "
            f"{len(devices)} firewall(s).[/bold]"
        )
        for dev, plan_obj in zip(devices, plans):
            _render_plan(plan_obj, title=f"Plan: {dev.name}")
    else:
        _render_plan(plans[0])


@app.command()
def apply(
    yes: bool = typer.Option(
        False, "--yes", "-y", help="Skip the interactive confirmation."
    ),
) -> None:
    """Apply shared services + per-device policies to every inventory firewall."""
    _validate_or_exit()
    state = load_desired_state()
    rules = load_rules()
    plans, devices = combined_plan(state)

    total_changed = sum(len(p.changed) for p in plans)
    if devices:
        console.print(
            f"[bold]Shared services ({len(state.services)}) → all "
            f"{len(devices)} firewall(s)[/bold]"
        )
        for dev, plan_obj in zip(devices, plans):
            if plan_obj.changed:
                _render_plan(plan_obj, title=f"Plan: {dev.name}")
    elif plans[0].changed:
        _render_plan(plans[0])

    if total_changed == 0:
        console.print("Nothing to apply.")
        return

    tripwire = rules.get("max_changes_per_apply", 10)
    for dev, plan_obj in zip(devices or [None], plans):
        n = len(plan_obj.changed)
        if n > tripwire:
            label = dev.name if dev else "default"
            console.print(
                f"[bold red]Refusing to apply {n} changes on {label} "
                f"(max_changes_per_apply={tripwire}).[/bold red]"
            )
            raise typer.Exit(code=2)

    if not yes:
        confirm = typer.confirm(f"Apply {total_changed} change(s)?")
        if not confirm:
            console.print("Aborted.")
            raise typer.Exit(code=0)

    for line in apply_all_devices(state):
        console.print(line)
        if "[ERROR]" in line:
            sys.exit(1)


@app.command()
def expiry_check(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Print alerts without posting to Slack."
    ),
) -> None:
    """List (or Slack-notify) temporary policies due for expiry alerts today."""
    state = load_desired_state()
    rules = load_rules()
    cfg = load_expiry_config(rules)
    alerts = policies_due_for_alert(state.policies, cfg)
    if not alerts:
        console.print("[green]No expiry alerts due today.[/green]")
        return
    for alert in alerts:
        pol = alert.policy
        console.print(
            f"[yellow]{alert.kind}[/yellow] "
            f"{pol.name} ({pol.device or 'default'}) "
            f"expires {pol.expires_at} — {alert.days_until} day(s) left"
        )
    if dry_run:
        return
    from slack_bot.notify_expiry import main as notify_main

    raise typer.Exit(notify_main([]))


@routes_app.callback(invoke_without_command=True)
def routes_show(ctx: typer.Context) -> None:
    """Show reference routing tables from config/devices.yaml."""
    if ctx.invoked_subcommand is not None:
        return
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


@routes_app.command("sync")
def routes_sync(
    write: bool = typer.Option(
        True,
        "--write/--dry-run",
        help="Write refreshed routes back to devices.yaml (default: write).",
    ),
) -> None:
    """Refresh devices.yaml routes from live GET /api/v2/monitor/router/lookup.

    Probes each IP in ``route_probes`` (and address-book subnets) on every
    inventory firewall, then stores the merged results as the offline reference.
    """
    probes = load_route_probes_from_repo()
    console.print(
        f"[bold]Probing {len(probes)} destination(s) per firewall "
        f"via monitor/router/lookup[/bold]"
    )
    try:
        per_device = sync_routes_file(write=write, probe_ips=probes)
    except RuntimeError as exc:
        console.print(f"[bold red]{exc}[/bold red]")
        raise typer.Exit(code=1) from exc

    for name, routes in per_device.items():
        console.print(f"  [green]{name}[/green]: {len(routes)} route(s)")
    if write:
        console.print("[bold green]Updated config/devices.yaml[/bold green]")
    else:
        console.print("[dim]Dry-run: devices.yaml not modified[/dim]")


@routes_app.command("probe")
def routes_probe(
    destination: str = typer.Argument(..., help="Destination IP to look up"),
    device: str = typer.Option(
        None, "--device", "-d", help="Inventory name (default: all devices)"
    ),
) -> None:
    """Show live router/lookup results across inventory firewalls."""
    devices = load_devices_live()
    if device:
        devices = [d for d in devices if d.name == device]
    if not devices:
        console.print("[bold red]No matching device(s).[/bold red]")
        raise typer.Exit(code=1)

    table = Table(title=f"router/lookup destination={destination}")
    table.add_column("Firewall")
    table.add_column("Network")
    table.add_column("Interface")
    table.add_column("Type")
    table.add_column("Gateway")
    table.add_column("Source")
    for dev in devices:
        route = dev.lookup(destination)
        if route is None:
            table.add_row(dev.name, "-", "-", "-", "-", "[red]no route[/red]")
            continue
        source = (
            "[cyan]live API[/cyan]"
            if dev.client is not None
            else "[dim]yaml cache[/dim]"
        )
        table.add_row(
            dev.name,
            route.dst,
            route.interface,
            route.type,
            route.gateway or "-",
            source,
        )
    console.print(table)


def _render_selection(
    title: str, selection, console: Console | None = None
) -> None:
    out = console or Console()
    targets = selection.transit
    table = Table(title=title)
    table.add_column("Firewall")
    table.add_column("src route")
    table.add_column("dst route")
    table.add_column("Verdict")
    for m in selection.matches:
        verdict = (
            "[bold green]TARGET[/bold green]"
            if m.is_transit
            else "[dim]skip[/dim]"
        )
        table.add_row(
            m.device,
            _route_cell(m.src_route),
            _route_cell(m.dst_route),
            f"{verdict}  [dim]{m.reason}[/dim]",
        )
    out.print(table)
    if not targets:
        out.print("  [bold red]No firewall is on the path.[/bold red]")
    else:
        for m in targets:
            ci = m.src_route.interface  # type: ignore[union-attr]
            co = m.dst_route.interface  # type: ignore[union-attr]
            out.print(
                f"  -> target: [bold green]{m.device}[/bold green] "
                f"(srcintf={ci}, dstintf={co})"
            )
    out.print()


@app.command()
def lookup(
    src: str = typer.Option(..., "--src", help="Source IP or CIDR"),
    dst: str = typer.Option(..., "--dst", help="Destination IP or CIDR"),
) -> None:
    """Show transit firewalls for arbitrary src/dst IPs (all devices.yaml entries).

    Unlike ``select``, this does not read firewall_policies.yaml — use it to
    verify ch/svr/vdi/dmz/cc routing for zone IPs such as 10.51.10.1 -> 10.56.10.1.
    """
    devices = load_devices_live()
    if not devices:
        console.print(
            "[bold red]No devices found in config/devices.yaml.[/bold red]"
        )
        raise typer.Exit(code=1)

    state = load_desired_state()
    addr_objs = [a.model_dump() for a in state.addresses]
    src_name = resolve_one(src, addr_objs) or src
    dst_name = resolve_one(dst, addr_objs) or dst
    addr_index = {a.name: a for a in state.addresses}
    if src_name not in addr_index:
        addr_index[src_name] = Address(name=src_name, type="ipmask", subnet=src)
    if dst_name not in addr_index:
        addr_index[dst_name] = Address(name=dst_name, type="ipmask", subnet=dst)

    probe = Policy(
        name="_lookup",
        srcintf=["auto"],
        dstintf=["auto"],
        srcaddr=[src_name],
        dstaddr=[dst_name],
        service=["HTTPS"],
    )
    selection = select_targets(probe, addr_index, devices)
    _render_selection(f"Lookup {src} -> {dst}", selection, console)


@app.command()
def select() -> None:
    """Pick the target firewall for each policy from its routing path.

    Uses config/devices.yaml. In dry-run mode the routing tables defined there
    are used; otherwise the live device's route lookup would be queried.
    """
    state = load_desired_state()
    devices = load_devices_live()
    if not devices:
        console.print(
            "[bold red]No devices found in config/devices.yaml.[/bold red]"
        )
        raise typer.Exit(code=1)

    addr_index = {a.name: a for a in state.addresses}

    for policy in state.policies:
        selection = select_targets(policy, addr_index, devices)
        _render_selection(
            f"Policy '{policy.name}'  ({_endpoints(policy)})",
            selection,
            console,
        )


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
