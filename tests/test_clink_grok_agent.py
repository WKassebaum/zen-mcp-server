"""Tests for the Grok Build CLI agent."""

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from clink.agents.base import CLIAgentError
from clink.agents.grok import GrokAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole


class DummyProcess:
    def __init__(self, *, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self, input_data=None):
        return self._stdout, self._stderr


@pytest.fixture()
def grok_agent():
    prompt_path = Path("systemprompts/clink/default.txt").resolve()
    role = ResolvedCLIRole(name="default", prompt_path=prompt_path, role_args=[])
    client = ResolvedCLIClient(
        name="grok",
        executable=["grok"],
        internal_args=["--output-format", "json"],
        config_args=["--permission-mode", "acceptEdits"],
        env={},
        timeout_seconds=30,
        parser="grok_json",
        runner="grok",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )
    return GrokAgent(client), role


async def _run_agent_with_process(monkeypatch, agent, role, process, *, system_prompt="System prompt"):
    async def fake_create_subprocess_exec(*_args, **_kwargs):
        return process

    def fake_which(executable_name):
        return f"/usr/bin/{executable_name}"

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    monkeypatch.setattr(shutil, "which", fake_which)

    return await agent.run(
        role=role,
        prompt="Respond with 42",
        system_prompt=system_prompt,
        files=[],
        images=[],
    )


@pytest.mark.asyncio
async def test_grok_agent_injects_rules_and_single_flag(monkeypatch, grok_agent):
    agent, role = grok_agent
    stdout_payload = json.dumps({"text": "42", "stopReason": "EndTurn"}).encode()
    process = DummyProcess(stdout=stdout_payload)

    result = await _run_agent_with_process(monkeypatch, agent, role, process)

    # Role/system prompt is appended via --rules (grok's --append-system-prompt analog)
    assert "--rules" in result.sanitized_command
    idx = result.sanitized_command.index("--rules")
    assert result.sanitized_command[idx + 1] == "System prompt"

    # The prompt must be the value of the trailing --single flag (headless mode),
    # otherwise grok would treat it as an interactive TUI prompt.
    assert result.sanitized_command[-2] == "--single"
    assert result.sanitized_command[-1] == "Respond with 42"

    assert result.parsed.content == "42"
    assert result.parsed.metadata["stop_reason"] == "EndTurn"


@pytest.mark.asyncio
async def test_grok_agent_propagates_unparseable_output(monkeypatch, grok_agent):
    agent, role = grok_agent
    process = DummyProcess(stdout=b"", returncode=1)

    with pytest.raises(CLIAgentError):
        await _run_agent_with_process(monkeypatch, agent, role, process)
