"""Command-line entry point.

    python -m tres_suite run  config.yaml            # full workflow: import, validate, analyse, export, plot
    python -m tres_suite inspect  path/to/file.xlsx  # print what the parser sees
    python -m tres_suite validate config.yaml        # import + validation only (no analysis, no writing)
    python -m tres_suite deconvolve OUT_DIR [--group "DOPC / 15"] [--replay decisions.json] [--no-prompt]
                                                     # advanced: terminal fit review of DAS log-normal deconvolution
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional, Sequence

from .config import load_config
from .export import _json_default, check_destination, write_run
from .pipeline import run_project
from .plotting import render_plots
from .validation import Severity
from .workbook import WorkbookParseError, load_workbook


def _print(s: str) -> None:
    print(s, file=sys.stderr, flush=True)


def cmd_inspect(args) -> int:
    for p in args.paths:
        try:
            wb = load_workbook(p)
            print(json.dumps({"path": p, **wb.summary_dict(), "warnings": wb.warnings}, indent=2, default=_json_default))
        except WorkbookParseError as exc:
            print(json.dumps({"path": p, "error": str(exc), "location": exc.location}, indent=2))
    return 0


def cmd_validate(args) -> int:
    cfg = load_config(args.config)
    cfg.tdfs_enabled = False
    from .pipeline import build_project
    from .validation import validate_group, compare_groups, group_is_blocked, project_level_checks

    project = build_project(cfg)
    diags = project_level_checks(project)
    project.load_all()
    ok_groups = []
    for g in project.groups():
        gd = validate_group(g, cfg.validation)
        diags.extend(gd)
        blocked = group_is_blocked(gd, g.group_id)
        print(f"{'BLOCKED' if blocked else 'ok     '}  {g.name}  ({len(g.measurements)} files)")
        if not blocked:
            ok_groups.append(g)
    diags.extend(compare_groups(ok_groups, cfg.validation))
    for d in diags:
        if d.severity != Severity.INFO or args.verbose:
            print(f"  [{d.severity.value}] {d.rule}: {d.message}")
    return 0


def cmd_run(args) -> int:
    cfg = load_config(args.config)
    if args.output:
        cfg.output.directory = args.output
    if args.overwrite:
        cfg.output.overwrite = True
    try:
        check_destination(cfg.output.directory, cfg.output.overwrite)
    except FileExistsError as exc:
        _print(f"{exc} (or pass --overwrite)")
        return 2
    result = run_project(cfg, _print if not args.quiet else None)
    plot_dir = os.path.join(cfg.output.directory, "plots")
    os.makedirs(cfg.output.directory, exist_ok=True)
    plot_outputs = []
    for pc in cfg.plots:
        try:
            plot_outputs.extend(render_plots(result, plot_dir, [pc]))
        except Exception as exc:  # a plot failure must not erase the run outputs
            _print(f"plot {pc.name} failed: {exc}")
            plot_outputs.append(type("PO", (), {"as_manifest": lambda self, e=exc, n=pc.name: {"name": n, "files": [], "description": f"FAILED: {e}"}})())
    manifest = write_run(result, cfg.output.directory, [p.as_manifest() for p in plot_outputs], check=False)
    _print(f"status: {result.status}; {manifest['n_errors']} errors, {manifest['n_warnings']} warnings; outputs in {cfg.output.directory}")
    for b in manifest["blocked_groups"]:
        _print(f"  blocked: {b['group']} ({', '.join(b['reasons'])})")
    return 0 if result.status != "failed" else 1


def cmd_deconvolve(args) -> int:
    from .advanced.deconvolution import run_deconvolution

    path = run_deconvolution(args.out_dir, args.group or None, args.replay, interactive=not args.no_prompt,
                             peaks_per_component=[int(x) for x in args.peaks.split(",")] if args.peaks else None)
    _print(f"decisions written to {path}; pass it with --replay to reproduce without prompts")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="tres_suite", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run the full workflow from a config file")
    r.add_argument("config")
    r.add_argument("--output", help="override output directory")
    r.add_argument("--overwrite", action="store_true")
    r.add_argument("--quiet", action="store_true")
    r.set_defaults(fn=cmd_run)
    v = sub.add_parser("validate", help="import and validate only")
    v.add_argument("config")
    v.add_argument("--verbose", action="store_true")
    v.set_defaults(fn=cmd_validate)
    i = sub.add_parser("inspect", help="show what the parser reads from workbooks")
    i.add_argument("paths", nargs="+")
    i.set_defaults(fn=cmd_inspect)
    d = sub.add_parser("deconvolve", help="advanced: interactive log-normal deconvolution review on a finished run")
    d.add_argument("out_dir", help="output directory of a finished run")
    d.add_argument("--group", action="append", help="group name (repeatable); default: every analysed TRES group")
    d.add_argument("--replay", help="deconvolution_decisions.json from an earlier review (no prompts)")
    d.add_argument("--no-prompt", action="store_true", help="accept the first fit of every component")
    d.add_argument("--peaks", help="initial peaks per component, e.g. 2,2,3")
    d.set_defaults(fn=cmd_deconvolve)
    args = ap.parse_args(argv)
    return args.fn(args)
