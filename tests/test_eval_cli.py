import json

from eval.cli import summarize


def test_summarize_groups_and_computes_tool_match() -> None:
    summary = summarize(
        [
            {
                "trace_id": "t1",
                "type": "baseline",
                "status": "ok",
                "tool_name": "search",
                "latency_ms": 10,
            },
            {
                "trace_id": "t1",
                "type": "candidate",
                "status": "ok",
                "tool_name": "search",
                "latency_ms": 20,
            },
            {
                "trace_id": "t2",
                "type": "baseline",
                "status": "ok",
                "tool_name": None,
                "latency_ms": 30,
            },
            {
                "trace_id": "t2",
                "type": "candidate",
                "status": "error",
                "tool_name": None,
                "latency_ms": 40,
            },
        ]
    )
    assert summary["paired_traces"] == 2
    assert summary["successful_pairs"] == 1
    assert summary["tool_comparable_pairs"] == 1
    assert summary["tool_match_percent"] == 100.0


def test_cli_judge_command_runs_with_json_config(tmp_path, capsys) -> None:
    log_path = tmp_path / "logs.jsonl"
    config_path = tmp_path / "judge_config.json"

    log_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "trace_id": "t1",
                        "type": "baseline",
                        "status": "ok",
                        "text": "restart service and inspect logs",
                        "tool_calls": [],
                    }
                ),
                json.dumps(
                    {
                        "trace_id": "t1",
                        "type": "candidate",
                        "status": "ok",
                        "text": "inspect logs after restarting service",
                        "tool_calls": [],
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )
    config_path.write_text(
        json.dumps(
            {
                "judges": [
                    {
                        "name": "semantic",
                        "type": "semantic_match",
                        "field": "text",
                        "threshold": 0.5,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    from eval.cli import main

    main(
        [
            "judge",
            "--file",
            str(log_path),
            "--config",
            str(config_path),
            "--semantic-backend",
            "token-overlap",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert output["summary"]["fully_passing_pairs"] == 1


def test_cli_summary_backwards_compatible_without_subcommand(tmp_path, capsys) -> None:
    log_path = tmp_path / "logs.jsonl"
    log_path.write_text(
        json.dumps(
            {
                "trace_id": "t1",
                "type": "baseline",
                "status": "ok",
                "tool_name": "search",
                "latency_ms": 10,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    from eval.cli import main

    main(["--file", str(log_path)])
    output = json.loads(capsys.readouterr().out)
    assert output["total_records"] == 1
