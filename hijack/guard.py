from __future__ import annotations

import json
from typing import Any

from .policy import (
    DEFAULT_AGENT_TOOL_POLICY,
    DEFAULT_DANGEROUS_TOOLS,
    DEFAULT_READ_TOOLS,
    DEFAULT_WRITE_TOOLS,
)


# 주어진 tool_name을 어떤 실행 에이전트가 담당하는지 정책에서 찾는다.
# 매핑이 없으면 unknown_agent를 반환한다.
def resolve_executor_agent(tool_name: str, policy: dict[str, set[str]] | None = None) -> str:
    tool_policy = policy or DEFAULT_AGENT_TOOL_POLICY
    for agent_name, allowed_tools in tool_policy.items():
        if tool_name in allowed_tools:
            return agent_name
    return "unknown_agent"


# R/W(읽기/쓰기) 분리 정책이 지켜지는지 검증한다.
# 하나의 에이전트가 read 도구와 write 도구를 동시에 가지면 실패한다.
def validate_rw_separation(
    policy: dict[str, set[str]] | None = None,
    read_tools: set[str] | None = None,
    write_tools: set[str] | None = None,
) -> tuple[bool, str]:
    tool_policy = policy or DEFAULT_AGENT_TOOL_POLICY
    reads = read_tools or DEFAULT_READ_TOOLS
    writes = write_tools or DEFAULT_WRITE_TOOLS

    for agent_name, allowed in tool_policy.items():
        if allowed & reads and allowed & writes:
            return False, f"R/W separation violation: {agent_name} can execute both read and write tools."
    return True, "ok"


# 오케스트레이터가 선택한 라우트 목록을 정제/검증한다.
# 1) 사용 가능한 라우트만 남기고, 2) 중복 제거, 3) 비어 있으면 rag로 안전 폴백.
# 추가로 감사용 안내 메시지(reasons)를 함께 반환한다.
def validate_orchestrator_routes(
    routes: list[str], available_routes: list[str], role: str
) -> tuple[list[str], list[str]]:
    reasons: list[str] = []
    valid = [r for r in routes if r in available_routes]
    valid = list(dict.fromkeys(valid))

    if not valid:
        reasons.append("No valid route from orchestrator output. Fallback to rag.")
        valid = ["rag"]

    if role != "admin" and "tool" in valid:
        reasons.append("User role uses tool route; role-based tool whitelist is applied.")

    return valid, reasons


# 실제 도구 실행 전에 공통 보안 검증을 수행한다.
# 검증 항목:
# - 허용된 도구인지
# - 실행 에이전트 매핑 존재 여부
# - R/W 분리 정책 위반 여부
# - role 기반 권한(admin 전용 도구 제한)
# - 인자 JSON 형식/타입 유효성
# - 과도한 문자열 길이/프롬프트 인젝션 패턴
#
# 반환:
# (검증성공여부, 메시지, 실행에이전트, 파싱된 인자dict)
def validate_tool_call(
    tool_call: dict[str, Any],
    role: str,
    allowed_tool_names: set[str],
    policy: dict[str, set[str]] | None = None,
) -> tuple[bool, str, str, dict[str, Any]]:
    name = tool_call.get("name", "")
    raw_args = tool_call.get("arguments", "{}")
    executor_agent = resolve_executor_agent(name, policy)

    if name not in allowed_tool_names:
        return False, "Unknown or unauthorized tool.", executor_agent, {}

    if executor_agent == "unknown_agent":
        return False, "No executor agent is mapped to this tool.", executor_agent, {}

    ok, rw_msg = validate_rw_separation(policy=policy)
    if not ok:
        return False, rw_msg, executor_agent, {}

    if role != "admin" and name in DEFAULT_WRITE_TOOLS:
        return False, "Write/exec tools are admin-only.", executor_agent, {}

    # tool_call.arguments는 문자열 JSON으로 들어올 수 있으므로 안전하게 파싱한다.
    try:
        parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
    except Exception:
        return False, "Invalid tool-call arguments JSON.", executor_agent, {}

    if not isinstance(parsed_args, dict):
        return False, "Tool-call arguments must be a JSON object.", executor_agent, {}

    for key, value in parsed_args.items():
        if isinstance(value, str) and len(value) > 5000:
            return False, f"Argument too large: {key}", executor_agent, {}
        if isinstance(value, str) and any(
            bad in value.lower() for bad in ["ignore previous", "system prompt", "developer prompt"]
        ):
            return False, "Potential prompt-injection text found in arguments.", executor_agent, {}

    return True, "ok", executor_agent, parsed_args


# 위험 도구 실행 전 사용자 확인 여부를 강제한다.
# 위험 도구가 아니면 즉시 통과, 위험 도구면 user_confirmed=True일 때만 통과.
# 실패 시 사용자에게 보여줄 요약 메시지를 반환한다.
def require_user_confirmation_for_risky_tool(
    tool_name: str,
    args: dict[str, Any],
    user_confirmed: bool,
    dangerous_tools: set[str] | None = None,
) -> tuple[bool, str]:
    danger = dangerous_tools or DEFAULT_DANGEROUS_TOOLS
    if tool_name not in danger:
        return True, "ok"

    if user_confirmed:
        return True, "ok"

    preview = ", ".join(f"{k}={str(v)[:80]}" for k, v in args.items())
    return False, f"User confirmation required for risky tool `{tool_name}`. args: {preview}"
