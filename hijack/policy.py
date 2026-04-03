from __future__ import annotations

DEFAULT_READ_TOOLS = {"read_file"}
DEFAULT_WRITE_TOOLS = {"write_file", "shell_exec", "python_eval"}
DEFAULT_DANGEROUS_TOOLS = {"shell_exec", "python_eval", "write_file"}

# 5-1. Enforce design-level separation between read and write executors.
DEFAULT_AGENT_TOOL_POLICY = {
    "tool_read_agent": {"read_file"},
    "tool_write_agent": {"write_file", "shell_exec", "python_eval"},
    "tool_common_agent": {"calc", "get_time"},
}
