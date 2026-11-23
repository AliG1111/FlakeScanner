#!/usr/bin/env python3
"""Check that requirements and implementation plan agree (traceability).

Every FR-/NFR- ID in docs/requirements.md must be cited by at least one task line in
docs/implementation-plan.md section 6, and its phase column must equal the set of phases
of the tasks that cite it ("All" is accepted as is). IDs cited in the plan must exist.

Usage:
  python3 -I tools/docs/check_trace.py         # report; exit 1 on any mismatch
  python3 -I tools/docs/check_trace.py --fix   # rewrite the phase column from the plan
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQ = ROOT / "docs" / "requirements.md"
PLAN = ROOT / "docs" / "implementation-plan.md"

ROW = re.compile(r"^\| (N?FR-[A-Z]+-\d\d) \|")
# FR-RMT-01, FR-RMT-01…12, NFR-SEC-01/03/06
CITE = re.compile(r"\b(N?FR-[A-Z]+)-(\d\d)((?:/\d\d)*)(?:…(\d\d))?\b")
PHASE_HEAD = re.compile(r"^### (P\d+)\b")


def phase_key(p: str) -> int:
    return int(p[1:])


def parse_phase_cell(cell: str) -> set[str] | None:
    """Phases named in a requirement's phase cell; None for 'All'."""
    if cell.strip() == "All":
        return None
    out: set[str] = set()
    for a, b in re.findall(r"P(\d+)(?:[–-]P(\d+))?", cell):
        if b:
            out.update(f"P{i}" for i in range(int(a), int(b) + 1))
        else:
            out.add(f"P{a}")
    return out


def cited_ids(text: str) -> list[str]:
    ids = []
    for prefix, first, slashes, last in CITE.findall(text):
        nums = [first] + [n for n in slashes.split("/") if n]
        if last:
            nums = [f"{i:02d}" for i in range(int(first), int(last) + 1)]
        ids.extend(f"{prefix}-{n}" for n in nums)
    return ids


def plan_citations() -> dict[str, set[str]]:
    lines = PLAN.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## 6."))
    end = next(i for i, l in enumerate(lines) if l.startswith("## 7."))
    phase = None
    cites: dict[str, set[str]] = {}
    for line in lines[start:end]:
        m = PHASE_HEAD.match(line)
        if m:
            phase = m.group(1)
            continue
        if phase and line.startswith("- "):
            for rid in cited_ids(line):
                cites.setdefault(rid, set()).add(phase)
    return cites


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fix", action="store_true", help="rewrite the phase column from the plan")
    args = ap.parse_args(argv)

    cites = plan_citations()
    req_lines = REQ.read_text(encoding="utf-8").splitlines(keepends=True)
    problems = []
    known = set()
    for i, line in enumerate(req_lines):
        m = ROW.match(line)
        if not m:
            continue
        rid = m.group(1)
        known.add(rid)
        cells = line.rstrip("\n").strip().strip("|").split("|")
        cell = cells[-2]
        stated = parse_phase_cell(cell)
        derived = cites.get(rid, set())
        if not derived:
            problems.append(f"{rid}: not cited by any task in the plan")
            continue
        if stated is None:
            continue
        if stated != derived:
            want = ", ".join(sorted(derived, key=phase_key))
            problems.append(f"{rid}: requirements say '{cell.strip()}', plan tasks give '{want}'")
            if args.fix:
                cells[-2] = f" {want} "
                req_lines[i] = "|" + "|".join(cells) + "|\n"
    for rid in sorted(set(cites) - known):
        problems.append(f"{rid}: cited in the plan but not defined in the requirements")

    if args.fix:
        REQ.write_text("".join(req_lines), encoding="utf-8")
    for p in problems:
        print(p)
    print(f"{len(known)} requirements, {len(problems)} problem(s)" + (" (phase cells rewritten)" if args.fix else ""))
    return 1 if problems and not args.fix else 0


if __name__ == "__main__":
    sys.exit(main())
