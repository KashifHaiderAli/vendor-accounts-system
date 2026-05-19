from __future__ import annotations

from dataclasses import asdict, dataclass
from html import escape
from pathlib import Path


@dataclass
class TestResult:
    step_no: int
    module: str
    action: str
    input_data: str
    expected: str
    actual: str
    status: str
    error: str = ""
    auto_fix_attempted: str = ""
    auto_fix_result: str = ""
    notes: str = ""


class ScenarioTestReport:
    def __init__(self, title: str, report_dir: Path, timestamp: str):
        self.title = title
        self.report_dir = report_dir
        self.timestamp = timestamp
        self.results: list[TestResult] = []
        self.environment: dict[str, str] = {}
        self.sections: dict[str, str] = {}

    def add(self, result: TestResult):
        self.results.append(result)

    def counts(self):
        statuses = ["PASS", "FAIL", "WARNING", "SKIPPED", "AUTO-FIXED"]
        return {status: sum(1 for item in self.results if item.status == status) for status in statuses}

    def conclusion(self):
        counts = self.counts()
        if counts["FAIL"]:
            return "NOT READY"
        if counts["WARNING"] or counts["SKIPPED"] or counts["AUTO-FIXED"]:
            return "READY WITH WARNINGS"
        return "READY"

    def write(self):
        self.report_dir.mkdir(parents=True, exist_ok=True)
        html_path = self.report_dir / f"full_system_scenario_test_{self.timestamp}.html"
        txt_path = self.report_dir / f"full_system_scenario_test_{self.timestamp}.txt"
        html_path.write_text(self.to_html(), encoding="utf-8")
        txt_path.write_text(self.to_text(), encoding="utf-8")
        return html_path, txt_path

    def to_html(self):
        counts = self.counts()
        env_rows = "".join(f"<tr><th>{escape(str(k))}</th><td>{escape(str(v))}</td></tr>" for k, v in self.environment.items())
        detail_rows = "".join(self.result_row(item) for item in self.results)
        sections = "".join(f"<h2>{escape(title)}</h2><div class='section'>{body}</div>" for title, body in self.sections.items())
        return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{escape(self.title)}</title>
<style>
body{{font-family:Segoe UI,Arial,sans-serif;margin:24px;background:#f6f8fb;color:#172033}}
h1,h2{{margin:0 0 12px}} h2{{margin-top:28px}}
.card{{background:white;border:1px solid #d8dee9;border-radius:8px;padding:16px;margin-bottom:16px}}
table{{width:100%;border-collapse:collapse;background:white}} th,td{{border:1px solid #d8dee9;padding:6px 8px;vertical-align:top;font-size:12px}} th{{background:#eef3fb;text-align:left}}
.badge{{display:inline-block;border-radius:999px;padding:2px 8px;font-weight:700;font-size:11px}}
.PASS{{background:#d9f7e8;color:#096b3b}} .FAIL{{background:#ffe0e0;color:#9d1b1b}} .WARNING{{background:#fff3cd;color:#7a5a00}}
.SKIPPED{{background:#e9ecef;color:#495057}} .AUTO-FIXED{{background:#d7ecff;color:#054f8b}}
.summary span{{margin-right:14px}} pre{{white-space:pre-wrap}}
</style></head><body>
<h1>{escape(self.title)}</h1>
<div class="card summary">
<strong>Conclusion:</strong> {escape(self.conclusion())}<br>
<span>Total: {len(self.results)}</span><span>Passed: {counts['PASS']}</span><span>Failed: {counts['FAIL']}</span>
<span>Warnings: {counts['WARNING']}</span><span>Skipped: {counts['SKIPPED']}</span><span>Auto-fixed: {counts['AUTO-FIXED']}</span>
</div>
<h2>Environment</h2><table>{env_rows}</table>
{sections}
<h2>Detailed Step-by-Step Results</h2>
<table><thead><tr><th>Step</th><th>Module</th><th>Action</th><th>Input</th><th>Expected</th><th>Actual</th><th>Status</th><th>Error / Fix</th></tr></thead><tbody>{detail_rows}</tbody></table>
</body></html>"""

    def result_row(self, item: TestResult):
        fix = "<br>".join(
            escape(value)
            for value in [
                item.error,
                f"Auto-fix attempted: {item.auto_fix_attempted}" if item.auto_fix_attempted else "",
                f"Auto-fix result: {item.auto_fix_result}" if item.auto_fix_result else "",
                item.notes,
            ]
            if value
        )
        return (
            f"<tr><td>{item.step_no}</td><td>{escape(item.module)}</td><td>{escape(item.action)}</td>"
            f"<td>{escape(item.input_data)}</td><td>{escape(item.expected)}</td><td>{escape(item.actual)}</td>"
            f"<td><span class='badge {item.status}'>{item.status}</span></td><td>{fix}</td></tr>"
        )

    def to_text(self):
        counts = self.counts()
        lines = [
            self.title,
            "=" * len(self.title),
            "",
            "Environment:",
            *[f"- {key}: {value}" for key, value in self.environment.items()],
            "",
            f"Executive Summary: total={len(self.results)} pass={counts['PASS']} fail={counts['FAIL']} warning={counts['WARNING']} skipped={counts['SKIPPED']} auto-fixed={counts['AUTO-FIXED']}",
            f"Final conclusion: {self.conclusion()}",
            "",
        ]
        for title, body in self.sections.items():
            lines.extend([title, "-" * len(title), body.replace("<br>", "\n"), ""])
        lines.append("Detailed Step-by-Step Results")
        lines.append("-----------------------------")
        for item in self.results:
            data = asdict(item)
            lines.append(f"Step {item.step_no} [{item.status}] {item.module} - {item.action}")
            for key in ["input_data", "expected", "actual", "error", "auto_fix_attempted", "auto_fix_result", "notes"]:
                if data.get(key):
                    lines.append(f"  {key}: {data[key]}")
            lines.append("")
        return "\n".join(lines)
