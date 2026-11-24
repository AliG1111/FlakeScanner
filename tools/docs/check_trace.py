#!/usr/bin/env python3
"""Check that requirements and implementation plan agree (traceability).

Every FR-/NFR- ID in docs/requirements/*.md must be defined once and cited by at least one
task line in docs/implementation-plan.md section 6, and its phase column must equal the set
of phases of the tasks that cite it ("All" is accepted as is). IDs cited in the plan must
exist. Every task line ("- [ ]" or "- [x]") cites at least one ID or is marked [process].

Usage:
  python3 -I tools/docs/check_trace.py         # report; exit 1 on any problem
  python3 -I tools/docs/check_trace.py --fix   # rewrite the phase column from the plan;
                                               # exit 1 if other problems remain
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REQ_DIR = ROOT / "docs" / "requirements"
PLAN = ROOT / "docs" / "implementation-plan.md"

# Requirement rows, tolerating bold and missing spaces: "| FR-APP-07 |", "| **FR-APP-07** |", "|FR-CAP-11|"
ROW = re.compile(r"^\|\s*\**\s*(N?FR-[A-Z]+-\d{2,3})\s*\**\s*\|")
TASK = re.compile(r"^- \[[ xX]\] ")
PROCESS = "[process]"
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


def plan_citations() -> tuple[dict[str, set[str]], list[str]]:
    """Phases citing each ID, and problems with task lines that cite nothing."""
    lines = PLAN.read_text(encoding="utf-8").splitlines()
    start = next(i for i, l in enumerate(lines) if l.startswith("## 6."))
    end = next(i for i, l in enumerate(lines) if l.startswith("## 7."))
    phase = None
    cites: dict[str, set[str]] = {}
    problems: list[str] = []
    for n, line in enumerate(lines[start:end], start=start + 1):
        m = PHASE_HEAD.match(line)
        if m:
            phase = m.group(1)
            continue
        if phase and line.startswith("- "):
            ids = cited_ids(line)
            for rid in ids:
                cites.setdefault(rid, set()).add(phase)
            if TASK.match(line) and not ids and PROCESS not in line:
                problems.append(f"plan line {n}: task cites no requirement and is not marked {PROCESS}: {line[:70]}")
    return cites, problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fix", action="store_true", help="rewrite the phase column from the plan")
    args = ap.parse_args(argv)

    cites, problems = plan_citations()
    fixable = 0
    known: dict[str, str] = {}
    for req_file in sorted(REQ_DIR.glob("*.md")):
        req_lines = req_file.read_text(encoding="utf-8").splitlines(keepends=True)
        changed = False
        for i, line in enumerate(req_lines):
            m = ROW.match(line)
            if not m:
                continue
            rid = m.group(1)
            where = f"{req_file.name}:{i + 1}"
            if rid in known:
                problems.append(f"{rid}: defined twice (requirements {known[rid]} and {where})")
                continue
            known[rid] = where
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
                fixable += 1
                if args.fix:
                    cells[-2] = f" {want} "
                    req_lines[i] = "|" + "|".join(cells) + "|\n"
                    changed = True
        if args.fix and changed:
            req_file.write_text("".join(req_lines), encoding="utf-8")
    for rid in sorted(set(cites) - set(known)):
        problems.append(f"{rid}: cited in the plan but not defined in the requirements")

    for p in problems:
        print(p)
    print(f"{len(known)} requirements, {len(problems)} problem(s)" + (" (phase cells rewritten)" if args.fix else ""))
    remaining = len(problems) - fixable if args.fix else len(problems)
    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
