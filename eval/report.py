from __future__ import annotations

import argparse
from pathlib import Path

from eval.report_models import BatchReport, LatencyStats, ReportData, ShadowReport
from eval.report_renderer import ReportRenderer
from eval.report_service import ReportService

_DEFAULT_REPORT_SERVICE = ReportService()
_DEFAULT_REPORT_RENDERER = ReportRenderer()


def build_shadow_report(path: Path) -> ShadowReport:
    return _DEFAULT_REPORT_SERVICE.build_shadow_report(path)


def build_batch_report(path: Path) -> BatchReport:
    return _DEFAULT_REPORT_SERVICE.build_batch_report(path)


def render_report_html(report: ReportData) -> str:
    return _DEFAULT_REPORT_RENDERER.render(report)


def build_report(
    *,
    file_path: Path,
    out_path: Path,
    batch_file: Path | None = None,
    title: str | None = None,
) -> ReportData:
    return _DEFAULT_REPORT_SERVICE.build_report(
        file_path=file_path,
        out_path=out_path,
        batch_file=batch_file,
        title=title,
        renderer=_DEFAULT_REPORT_RENDERER,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an HTML report for LLM shadow logs.")
    parser.add_argument("--file", required=True, help="Path to the shadow JSONL log file.")
    parser.add_argument("--out", required=True, help="Path to write the HTML report.")
    parser.add_argument("--batch-file", help="Optional OpenAI-style batch JSONL file.")
    parser.add_argument("--title", help="Optional report title.")
    args = parser.parse_args()

    build_report(
        file_path=Path(args.file),
        out_path=Path(args.out),
        batch_file=Path(args.batch_file) if args.batch_file else None,
        title=args.title,
    )


if __name__ == "__main__":
    main()
