from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from eval.accessors import get_path
from eval.matchers import exact_match, regex_match, semantic_match
from eval.semantic import SemanticBackend


@dataclass(slots=True)
class JudgeResult:
    name: str
    type: str
    passed: bool
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "type": self.type,
            "passed": self.passed,
            "details": self.details,
        }


class Judge(Protocol):
    name: str
    type: str

    def evaluate(
        self,
        baseline: dict[str, Any],
        candidate: dict[str, Any],
        *,
        semantic_backend: SemanticBackend,
    ) -> JudgeResult:
        ...


class RegexJudge:
    type = "regex_match"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name = config["name"]

    def evaluate(
        self,
        baseline: dict[str, Any],
        candidate: dict[str, Any],
        *,
        semantic_backend: SemanticBackend,
    ) -> JudgeResult:
        field = self.config.get("field", "text")
        actual = get_path(candidate, field)
        passed = regex_match(self.config["pattern"], actual)
        return JudgeResult(
            name=self.name,
            type=self.type,
            passed=passed,
            details={"field": field, "actual": actual, "pattern": self.config["pattern"]},
        )


class SemanticJudge:
    type = "semantic_match"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name = config["name"]

    def evaluate(
        self,
        baseline: dict[str, Any],
        candidate: dict[str, Any],
        *,
        semantic_backend: SemanticBackend,
    ) -> JudgeResult:
        field = self.config.get("field", "text")
        baseline_value = get_path(baseline, field)
        candidate_value = get_path(candidate, field)
        passed, score = semantic_match(
            baseline_value,
            candidate_value,
            backend=semantic_backend,
            threshold=self.config.get("threshold", 0.9),
            rubric=self.config.get("rubric"),
        )
        return JudgeResult(
            name=self.name,
            type=self.type,
            passed=passed,
            details={
                "field": field,
                "baseline": baseline_value,
                "candidate": candidate_value,
                "score": score,
            },
        )


class ToolCallMatcher:
    def __init__(self, *, semantic_backend: SemanticBackend) -> None:
        self._semantic_backend = semantic_backend
        self._bindings: dict[str, Any] = {}

    def match(
        self,
        *,
        call_spec: dict[str, Any],
        baseline_call: dict[str, Any],
        candidate_call: dict[str, Any],
    ) -> tuple[bool, dict[str, Any]]:
        expected_name = call_spec.get("name")
        if expected_name is not None:
            if (
                baseline_call.get("name") != expected_name
                or candidate_call.get("name") != expected_name
            ):
                return False, {
                    "reason": "tool_name_mismatch",
                    "expected_name": expected_name,
                    "baseline_name": baseline_call.get("name"),
                    "candidate_name": candidate_call.get("name"),
                }
        elif baseline_call.get("name") != candidate_call.get("name"):
            return False, {
                "reason": "tool_name_mismatch",
                "baseline_name": baseline_call.get("name"),
                "candidate_name": candidate_call.get("name"),
            }

        argument_spec = call_spec.get("arguments")
        if argument_spec is None:
            if baseline_call.get("arguments") != candidate_call.get("arguments"):
                return False, {
                    "reason": "tool_arguments_mismatch",
                    "baseline_arguments": baseline_call.get("arguments"),
                    "candidate_arguments": candidate_call.get("arguments"),
                }
            return True, {}

        return self._match_argument_spec(
            argument_spec,
            baseline_call.get("arguments"),
            candidate_call.get("arguments"),
            path="arguments",
        )

    @property
    def bindings(self) -> dict[str, Any]:
        return dict(self._bindings)

    def extract_tool_calls(self, record: dict[str, Any]) -> list[dict[str, Any]]:
        tool_calls = record.get("tool_calls")
        if isinstance(tool_calls, list):
            return tool_calls

        tool_name = record.get("tool_name")
        if tool_name is None:
            return []
        return [{"name": tool_name, "arguments": record.get("tool_args")}]

    def _match_argument_spec(
        self,
        spec: Any,
        baseline_value: Any,
        candidate_value: Any,
        *,
        path: str,
    ) -> tuple[bool, dict[str, Any]]:
        if isinstance(spec, dict) and "var" in spec:
            return self._match_variable_spec(
                spec,
                baseline_value,
                candidate_value,
                path=path,
            )

        if isinstance(spec, dict):
            if not isinstance(baseline_value, dict) or not isinstance(candidate_value, dict):
                return False, {
                    "reason": "argument_shape_mismatch",
                    "path": path,
                    "baseline": baseline_value,
                    "candidate": candidate_value,
                }
            for key, child_spec in spec.items():
                if key not in baseline_value or key not in candidate_value:
                    return False, {
                        "reason": "missing_argument_key",
                        "path": f"{path}.{key}",
                        "baseline": baseline_value,
                        "candidate": candidate_value,
                    }
                matched, details = self._match_argument_spec(
                    child_spec,
                    baseline_value[key],
                    candidate_value[key],
                    path=f"{path}.{key}",
                )
                if not matched:
                    return False, details
            return True, {}

        if isinstance(spec, list):
            if not isinstance(baseline_value, list) or not isinstance(candidate_value, list):
                return False, {
                    "reason": "argument_shape_mismatch",
                    "path": path,
                    "baseline": baseline_value,
                    "candidate": candidate_value,
                }
            if len(spec) != len(baseline_value) or len(spec) != len(candidate_value):
                return False, {
                    "reason": "argument_list_length_mismatch",
                    "path": path,
                    "expected_length": len(spec),
                    "baseline_length": len(baseline_value),
                    "candidate_length": len(candidate_value),
                }
            for index, child_spec in enumerate(spec):
                matched, details = self._match_argument_spec(
                    child_spec,
                    baseline_value[index],
                    candidate_value[index],
                    path=f"{path}.{index}",
                )
                if not matched:
                    return False, details
            return True, {}

        if baseline_value != spec or candidate_value != spec:
            return False, {
                "reason": "literal_mismatch",
                "path": path,
                "expected": spec,
                "baseline": baseline_value,
                "candidate": candidate_value,
            }
        return True, {}

    def _match_variable_spec(
        self,
        spec: dict[str, Any],
        baseline_value: Any,
        candidate_value: Any,
        *,
        path: str,
    ) -> tuple[bool, dict[str, Any]]:
        variable_name = spec["var"]
        match_mode = spec.get("match", "exact")

        if variable_name in self._bindings:
            expected_value = self._bindings[variable_name]
            if baseline_value != expected_value:
                return False, {
                    "reason": "baseline_binding_mismatch",
                    "path": path,
                    "variable": variable_name,
                    "expected": expected_value,
                    "baseline": baseline_value,
                }
        else:
            self._bindings[variable_name] = baseline_value
            expected_value = baseline_value

        if match_mode == "exact":
            passed = candidate_value == expected_value
            score = None
        elif match_mode == "regex":
            if not isinstance(expected_value, str):
                return False, {
                    "reason": "regex_variable_not_string",
                    "path": path,
                    "variable": variable_name,
                    "baseline": baseline_value,
                }
            passed = regex_match(expected_value, candidate_value)
            score = None
        elif match_mode == "semantic":
            passed, score = semantic_match(
                expected_value,
                candidate_value,
                backend=self._semantic_backend,
                threshold=spec.get("threshold", 0.9),
                rubric=spec.get("rubric"),
            )
        else:
            return False, {
                "reason": "unsupported_match_mode",
                "path": path,
                "match_mode": match_mode,
            }

        if not passed:
            return False, {
                "reason": "variable_mismatch",
                "path": path,
                "variable": variable_name,
                "expected": expected_value,
                "candidate": candidate_value,
                "match_mode": match_mode,
                "score": score,
            }
        return True, {}


class ToolCallJudge:
    type = "tool_call_match"

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.name = config["name"]

    def evaluate(
        self,
        baseline: dict[str, Any],
        candidate: dict[str, Any],
        *,
        semantic_backend: SemanticBackend,
    ) -> JudgeResult:
        matcher = ToolCallMatcher(semantic_backend=semantic_backend)
        baseline_calls = matcher.extract_tool_calls(baseline)
        candidate_calls = matcher.extract_tool_calls(candidate)
        spec_calls = self.config.get("tool_calls")

        if spec_calls is None:
            return JudgeResult(
                name=self.name,
                type=self.type,
                passed=exact_match(baseline_calls, candidate_calls),
                details={"baseline": baseline_calls, "candidate": candidate_calls},
            )

        if len(baseline_calls) != len(spec_calls) or len(candidate_calls) != len(spec_calls):
            return JudgeResult(
                name=self.name,
                type=self.type,
                passed=False,
                details={
                    "reason": "tool_call_count_mismatch",
                    "expected_count": len(spec_calls),
                    "baseline_count": len(baseline_calls),
                    "candidate_count": len(candidate_calls),
                },
            )

        for index, call_spec in enumerate(spec_calls):
            call_passed, details = matcher.match(
                call_spec=call_spec,
                baseline_call=baseline_calls[index],
                candidate_call=candidate_calls[index],
            )
            if not call_passed:
                return JudgeResult(
                    name=self.name,
                    type=self.type,
                    passed=False,
                    details={"call_index": index, **details},
                )

        return JudgeResult(
            name=self.name,
            type=self.type,
            passed=True,
            details={"bindings": matcher.bindings},
        )


class JudgeFactory:
    def __init__(self) -> None:
        self._registry: dict[str, type[Judge]] = {
            RegexJudge.type: RegexJudge,
            SemanticJudge.type: SemanticJudge,
            ToolCallJudge.type: ToolCallJudge,
        }

    def create(self, config: dict[str, Any]) -> Judge:
        judge_type = config["type"]
        judge_class = self._registry.get(judge_type)
        if judge_class is None:
            raise ValueError(f"Unsupported judge type: {judge_type}")
        return judge_class(config)


DEFAULT_JUDGE_FACTORY = JudgeFactory()


def evaluate_judge(
    judge: dict[str, Any],
    baseline: dict[str, Any],
    candidate: dict[str, Any],
    *,
    semantic_backend: SemanticBackend,
) -> dict[str, Any]:
    return DEFAULT_JUDGE_FACTORY.create(judge).evaluate(
        baseline,
        candidate,
        semantic_backend=semantic_backend,
    ).to_dict()
