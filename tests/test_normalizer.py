from normalizer.normalize import normalize


def test_normalize_text_only_response() -> None:
    response = {"choices": [{"message": {"content": "hello"}}]}
    assert normalize(response) == {
        "text": "hello",
        "tool_name": None,
        "tool_args": None,
        "tool_calls": [],
    }


def test_normalize_first_tool_call() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {"function": {"name": "search", "arguments": '{"q":"weather"}'}},
                        {"function": {"name": "ignored", "arguments": "{}"}},
                    ],
                }
            }
        ]
    }
    assert normalize(response) == {
        "text": None,
        "tool_name": "search",
        "tool_args": {"q": "weather"},
        "tool_calls": [
            {"name": "search", "arguments": {"q": "weather"}},
            {"name": "ignored", "arguments": {}},
        ],
    }


def test_normalize_invalid_tool_arguments_returns_raw_string() -> None:
    response = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {"function": {"name": "search", "arguments": "{bad json"}},
                    ]
                }
            }
        ]
    }
    assert normalize(response)["tool_args"] == "{bad json"
    assert normalize(response)["tool_calls"] == [{"name": "search", "arguments": "{bad json"}]


def test_normalize_missing_choices_returns_null_fields() -> None:
    assert normalize({}) == {"text": None, "tool_name": None, "tool_args": None, "tool_calls": []}


def test_normalize_missing_message_content_and_tools_returns_nulls() -> None:
    response = {"choices": [{"message": {}}]}
    assert normalize(response) == {
        "text": None,
        "tool_name": None,
        "tool_args": None,
        "tool_calls": [],
    }
