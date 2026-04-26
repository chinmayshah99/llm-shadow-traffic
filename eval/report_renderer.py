from __future__ import annotations

import json
from html import escape
from typing import Any

from eval.report_models import ReportData


def _truncate(value: Any, limit: int = 120) -> str:
    text = "" if value is None else str(value)
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def _json_preview(value: Any, limit: int = 120) -> str:
    if value is None:
        return ""
    try:
        text = json.dumps(value, sort_keys=True)
    except TypeError:
        text = str(value)
    return _truncate(text, limit)


def _format_metric(value: Any, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        text = f"{value:.2f}".rstrip("0").rstrip(".")
    else:
        text = str(value)
    return f"{text}{suffix}"


def _render_cards(cards: list[tuple[str, str]]) -> str:
    return "".join(
        f"""
        <div class="card">
          <div class="card-label">{escape(label)}</div>
          <div class="card-value">{escape(value)}</div>
        </div>
        """
        for label, value in cards
    )


def _render_table(headers: list[str], rows: list[list[str]]) -> str:
    header_html = "".join(f"<th>{escape(header)}</th>" for header in headers)
    if not rows:
        return '<div class="empty">No data available.</div>'
    body_html = "".join(
        "<tr>" + "".join(f"<td>{escape(cell)}</td>" for cell in row) + "</tr>"
        for row in rows
    )
    return f"""
    <table>
      <thead>
        <tr>{header_html}</tr>
      </thead>
      <tbody>
        {body_html}
      </tbody>
    </table>
    """


def _render_breakdown(rows: list[dict[str, Any]], label_key: str, value_key: str) -> str:
    if not rows:
        return '<div class="empty">No data available.</div>'
    max_value = max(int(row[value_key]) for row in rows) or 1
    items = []
    for row in rows:
        width = int(int(row[value_key]) / max_value * 100)
        items.append(
            f"""
            <div class="bar-row">
              <div class="bar-label">{escape(str(row[label_key]))}</div>
              <div class="bar-track"><div class="bar-fill" style="width: {width}%"></div></div>
              <div class="bar-value">{escape(str(row[value_key]))}</div>
            </div>
            """
        )
    return "".join(items)


class ReportRenderer:
    def render(self, report: ReportData) -> str:
        shadow = report.shadow
        batch = report.batch
        summary_cards = [
            ("Total records", _format_metric(shadow.total_records)),
            ("Paired traces", _format_metric(shadow.paired_traces)),
            ("Successful pairs", _format_metric(shadow.successful_pairs)),
            ("Tool match", _format_metric(shadow.tool_match_percent, "%")),
            ("Candidate avg latency", _format_metric(shadow.candidate_latency.avg_ms, " ms")),
            ("Candidate error rate", _format_metric(shadow.candidate_error_rate, "%")),
        ]
        status_rows = [
            {"label": f'{row["type"]}: {row["status"]}', "count": row["count"]}
            for row in shadow.status_breakdown
        ]
        tool_rows = [
            {"label": f'{row["type"]}: {row["tool_name"]}', "count": row["count"]}
            for row in shadow.top_tools
        ]

        batch_html = ""
        if batch is not None:
            batch_cards = [
                ("Batch rows", _format_metric(batch.row_count)),
                ("Batch successes", _format_metric(batch.success_count)),
                ("Batch errors", _format_metric(batch.error_count)),
                ("Batch error rate", _format_metric(batch.error_rate, "%")),
                (
                    "Batch avg latency",
                    _format_metric(batch.latency.avg_ms, " ms") if batch.latency else "n/a",
                ),
            ]
            batch_note = ""
            if batch.limited_fields_detected:
                batch_note = (
                    "<p class=\"note\">Limited batch fields detected; the report only shows metrics "
                    f"available in this file ({escape(', '.join(batch.detected_fields) or 'none')}).</p>"
                )
            batch_html = f"""
            <section>
              <h2>Batch Summary</h2>
              <div class="cards">{_render_cards(batch_cards)}</div>
              {batch_note}
              <div class="grid-two">
                <div class="panel">
                  <h3>Model Distribution</h3>
                  {_render_breakdown(batch.model_distribution, "model", "count")}
                </div>
                <div class="panel">
                  <h3>Latency</h3>
                  <div class="stats-list">
                    <div>Average: <strong>{escape(_format_metric(batch.latency.avg_ms, ' ms') if batch.latency else 'n/a')}</strong></div>
                    <div>P50: <strong>{escape(_format_metric(batch.latency.p50_ms, ' ms') if batch.latency else 'n/a')}</strong></div>
                    <div>P95: <strong>{escape(_format_metric(batch.latency.p95_ms, ' ms') if batch.latency else 'n/a')}</strong></div>
                  </div>
                </div>
              </div>
              <div class="panel">
                <h3>Batch Sample</h3>
                {_render_table(
                    ["Custom ID", "Status", "HTTP", "Model", "Tool", "Tokens", "Text", "Error"],
                    [
                        [
                            _truncate(row["custom_id"], 40),
                            _truncate(row["status"], 20),
                            _truncate(row["status_code"], 20),
                            _truncate(row["model"], 30),
                            _truncate(row["tool_name"], 30),
                            _truncate(row["total_tokens"], 20),
                            _truncate(row["text"], 80),
                            _truncate(row["error_message"], 80),
                        ]
                        for row in batch.sample_rows
                    ],
                )}
              </div>
            </section>
            """

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(report.title)}</title>
  <style>
    :root {{
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --ink: #1f2933;
      --muted: #5c6b73;
      --line: #d8d2c8;
      --accent: #b25538;
      --accent-soft: #f0c9b9;
      --ok: #2f855a;
      --warn: #b7791f;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Iowan Old Style", "Palatino Linotype", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(178, 85, 56, 0.12), transparent 28%),
        linear-gradient(180deg, #faf7f2 0%, var(--bg) 100%);
    }}
    .shell {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    header {{
      margin-bottom: 24px;
      padding: 24px;
      background: rgba(255, 253, 248, 0.92);
      border: 1px solid var(--line);
      border-radius: 18px;
    }}
    h1, h2, h3 {{
      margin: 0 0 10px;
      font-weight: 700;
      line-height: 1.1;
    }}
    h1 {{ font-size: 2.4rem; }}
    h2 {{ font-size: 1.5rem; margin-bottom: 14px; }}
    h3 {{ font-size: 1.05rem; color: var(--muted); }}
    p {{ margin: 0; line-height: 1.5; }}
    section {{ margin-top: 22px; }}
    .subtitle {{
      color: var(--muted);
      margin-top: 8px;
    }}
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 14px;
    }}
    .card, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 16px;
      box-shadow: 0 10px 30px rgba(31, 41, 51, 0.05);
    }}
    .card-label {{
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .card-value {{
      margin-top: 8px;
      font-size: 1.8rem;
      font-weight: 700;
    }}
    .grid-two {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 16px;
    }}
    .stats-list {{
      display: grid;
      gap: 10px;
      font-size: 1rem;
    }}
    .bar-row {{
      display: grid;
      grid-template-columns: minmax(120px, 180px) 1fr auto;
      gap: 10px;
      align-items: center;
      margin-bottom: 12px;
    }}
    .bar-label, .bar-value {{
      font-size: 0.95rem;
      color: var(--muted);
    }}
    .bar-track {{
      height: 10px;
      border-radius: 999px;
      background: #ece5dc;
      overflow: hidden;
    }}
    .bar-fill {{
      height: 100%;
      background: linear-gradient(90deg, var(--accent), #d88a6e);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
      text-align: left;
    }}
    th {{
      color: var(--muted);
      font-size: 0.85rem;
      letter-spacing: 0.03em;
      text-transform: uppercase;
    }}
    .empty, .note {{
      color: var(--muted);
      font-size: 0.95rem;
    }}
    .note {{
      margin: 12px 0 0;
    }}
    @media (max-width: 700px) {{
      .shell {{ padding: 20px 14px 36px; }}
      h1 {{ font-size: 1.8rem; }}
      .bar-row {{
        grid-template-columns: 1fr;
        gap: 6px;
      }}
      table, thead, tbody, th, td, tr {{
        display: block;
      }}
      thead {{
        display: none;
      }}
      tr {{
        border-bottom: 1px solid var(--line);
        padding: 8px 0;
      }}
      td {{
        border: 0;
        padding: 6px 0;
      }}
    }}
  </style>
</head>
<body>
  <div class="shell">
    <header>
      <h1>{escape(report.title)}</h1>
      <p class="subtitle">Generated at {escape(report.generated_at)} from shadow traffic JSONL logs.</p>
    </header>

    <section>
      <h2>Shadow Summary</h2>
      <div class="cards">{_render_cards(summary_cards)}</div>
    </section>

    <section class="grid-two">
      <div class="panel">
        <h2>Latency Comparison</h2>
        <div class="stats-list">
          <div>Baseline average: <strong>{escape(_format_metric(shadow.baseline_latency.avg_ms, ' ms'))}</strong></div>
          <div>Baseline P50 / P95: <strong>{escape(_format_metric(shadow.baseline_latency.p50_ms, ' ms'))}</strong> / <strong>{escape(_format_metric(shadow.baseline_latency.p95_ms, ' ms'))}</strong></div>
          <div>Candidate average: <strong>{escape(_format_metric(shadow.candidate_latency.avg_ms, ' ms'))}</strong></div>
          <div>Candidate P50 / P95: <strong>{escape(_format_metric(shadow.candidate_latency.p50_ms, ' ms'))}</strong> / <strong>{escape(_format_metric(shadow.candidate_latency.p95_ms, ' ms'))}</strong></div>
        </div>
      </div>
      <div class="panel">
        <h2>Tool Calls</h2>
        <div class="stats-list">
          <div>Comparable pairs: <strong>{escape(_format_metric(shadow.tool_comparable_pairs))}</strong></div>
          <div>Matching tool calls: <strong>{escape(_format_metric(shadow.tool_match_count))}</strong></div>
          <div>Match rate: <strong>{escape(_format_metric(shadow.tool_match_percent, '%'))}</strong></div>
        </div>
      </div>
    </section>

    <section class="grid-two">
      <div class="panel">
        <h2>Status Breakdown</h2>
        {_render_breakdown(status_rows, "label", "count")}
      </div>
      <div class="panel">
        <h2>Top Tool Names</h2>
        {_render_breakdown(tool_rows, "label", "count")}
      </div>
    </section>

    <section class="panel">
      <h2>Worst Candidate Latency Deltas</h2>
      {_render_table(
          ["Trace", "Baseline ms", "Candidate ms", "Delta ms", "Base status", "Cand status", "Base tool", "Cand tool"],
          [
              [
                  _truncate(row["trace_id"], 24),
                  _format_metric(row["baseline_latency_ms"]),
                  _format_metric(row["candidate_latency_ms"]),
                  _format_metric(row["latency_delta_ms"]),
                  _truncate(row["baseline_status"], 20),
                  _truncate(row["candidate_status"], 20),
                  _truncate(row["baseline_tool_name"], 30),
                  _truncate(row["candidate_tool_name"], 30),
              ]
              for row in shadow.worst_latency_deltas
          ],
      )}
    </section>

    <section class="grid-two">
      <div class="panel">
        <h2>Tool Mismatches</h2>
        {_render_table(
            ["Trace", "Baseline tool", "Candidate tool", "Baseline args", "Candidate args"],
            [
                [
                    _truncate(row["trace_id"], 24),
                    _truncate(row["baseline_tool_name"], 30),
                    _truncate(row["candidate_tool_name"], 30),
                    _json_preview(row["baseline_tool_args"]),
                    _json_preview(row["candidate_tool_args"]),
                ]
                for row in shadow.tool_mismatches
            ],
        )}
      </div>
      <div class="panel">
        <h2>Candidate Errors</h2>
        {_render_table(
            ["Trace", "Error type", "Message", "Latency ms", "Base status", "Cand status"],
            [
                [
                    _truncate(row["trace_id"], 24),
                    _truncate(row["candidate_error_type"], 30),
                    _truncate(row["candidate_error_message"], 80),
                    _format_metric(row["candidate_latency_ms"]),
                    _truncate(row["baseline_status"], 20),
                    _truncate(row["candidate_status"], 20),
                ]
                for row in shadow.candidate_errors
            ],
        )}
      </div>
    </section>

    <section class="panel">
      <h2>Recent Paired Traces</h2>
      {_render_table(
          ["Trace", "Base status", "Cand status", "Base ms", "Cand ms", "Base tool", "Cand tool", "Baseline text", "Candidate text"],
          [
              [
                  _truncate(row["trace_id"], 24),
                  _truncate(row["baseline_status"], 20),
                  _truncate(row["candidate_status"], 20),
                  _format_metric(row["baseline_latency_ms"]),
                  _format_metric(row["candidate_latency_ms"]),
                  _truncate(row["baseline_tool_name"], 30),
                  _truncate(row["candidate_tool_name"], 30),
                  _truncate(row["baseline_text"], 80),
                  _truncate(row["candidate_text"], 80),
              ]
              for row in shadow.recent_pairs
          ],
      )}
    </section>

    {batch_html}
  </div>
</body>
</html>
"""
