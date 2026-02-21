"""Generate GitHub Actions step summary from pytest JUnit XML and coverage output.

Parses two artifacts produced by pytest during CI and renders them as
GitHub-flavored markdown tables written to ``$GITHUB_STEP_SUMMARY``.
When the environment variable is absent (local runs), output is printed
to stdout instead.

Expected Artifacts
------------------
report.xml
    JUnit XML produced by ``pytest --junitxml=report.xml``.
coverage-output.txt
    Terminal output captured from ``pytest --cov --cov-report=term-missing``.
"""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path


def parse_junit_xml(path: Path) -> str:
    """Parse JUnit XML report into a markdown table.

    Iterates over ``<testsuite>`` elements, aggregating pass/fail/skip
    counts and elapsed time into a summary table with a totals row.

    Parameters
    ----------
    path : Path
        Path to the JUnit XML file (e.g. ``report.xml``).

    Returns
    -------
    str
        Markdown table string, or an empty string if no test suites
        were found in the XML.
    """
    tree = ET.parse(path)  # noqa: S314
    root = tree.getroot()

    rows: list[tuple[str, int, int, int, str]] = []
    total_pass = total_fail = total_skip = 0
    total_time = 0.0

    for suite in root.iter("testsuite"):
        name = suite.get("name", "unknown")
        tests = int(suite.get("tests", 0))
        failures = int(suite.get("failures", 0))
        errors = int(suite.get("errors", 0))
        skipped = int(suite.get("skipped", 0))
        time_s = float(suite.get("time", 0))

        failed = failures + errors
        passed = tests - failed - skipped
        rows.append((name, passed, failed, skipped, f"{time_s:.2f}s"))

        total_pass += passed
        total_fail += failed
        total_skip += skipped
        total_time += time_s

    if not rows:
        return ""

    lines = [
        "## Test Results",
        "",
        "| Suite | Passed | Failed | Skipped | Time |",
        "|-------|--------|--------|---------|------|",
    ]
    for name, passed, failed, skipped, time_str in rows:
        lines.append(f"| {name} | {passed} | {failed} | {skipped} | {time_str} |")
    lines.append(
        f"| **Total** | **{total_pass}** | **{total_fail}** "
        f"| **{total_skip}** | **{total_time:.2f}s** |"
    )
    lines.append("")
    return "\n".join(lines)


def parse_coverage_output(path: Path) -> str:
    """Parse pytest-cov terminal output into a markdown table.

    Extracts per-file statement/miss/coverage rows and the TOTAL line
    from the ``term-missing`` report format produced by pytest-cov.

    Parameters
    ----------
    path : Path
        Path to the captured coverage output (e.g. ``coverage-output.txt``).

    Returns
    -------
    str
        Markdown table string, or an empty string if no coverage data
        was found in the file.
    """
    text = path.read_text()

    # Match lines like: src/lattice/core.py    42      3    93%
    pattern = re.compile(r"^(\S+\.py)\s+(\d+)\s+(\d+)\s+(\d+%)", re.MULTILINE)
    matches = pattern.findall(text)

    # Match TOTAL line
    total_pattern = re.compile(r"^TOTAL\s+(\d+)\s+(\d+)\s+(\d+%)", re.MULTILINE)
    total_match = total_pattern.search(text)

    if not matches and not total_match:
        return ""

    lines = [
        "## Coverage Report",
        "",
        "| File | Stmts | Miss | Cover |",
        "|------|-------|------|-------|",
    ]
    for file, stmts, miss, cover in matches:
        lines.append(f"| {file} | {stmts} | {miss} | {cover} |")
    if total_match:
        lines.append(
            f"| **TOTAL** | **{total_match.group(1)}** "
            f"| **{total_match.group(2)}** | **{total_match.group(3)}** |"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    """Assemble test and coverage summaries and write to the step summary.

    Looks for ``report.xml`` and ``coverage-output.txt`` in the current
    working directory.  If ``$GITHUB_STEP_SUMMARY`` is set, the rendered
    markdown is appended to that file; otherwise it is printed to stdout.
    """
    report_xml = Path("report.xml")
    coverage_txt = Path("coverage-output.txt")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY", "")

    parts: list[str] = []

    if report_xml.exists():
        result = parse_junit_xml(report_xml)
        if result:
            parts.append(result)

    if coverage_txt.exists():
        result = parse_coverage_output(coverage_txt)
        if result:
            parts.append(result)

    if not parts:
        parts.append("No test or coverage data found.")

    output = "\n".join(parts)

    if summary_path:
        with Path(summary_path).open("a") as f:
            f.write(output + "\n")
    else:
        print(output)


if __name__ == "__main__":
    main()
