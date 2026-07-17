"""Unit tests for clink runtime --model override."""

import asyncio
import json
import shutil
from pathlib import Path

import pytest

from clink.agents.base import BaseCLIAgent
from clink.agents.claude import ClaudeAgent
from clink.agents.grok import GrokAgent
from clink.models import ResolvedCLIClient, ResolvedCLIRole


def _role():
    return ResolvedCLIRole(
        name="default",
        prompt_path=Path("systemprompts/clink/default.txt").resolve(),
        role_args=[],
    )


def _claude_client_with_pinned_sonnet():
    role = _role()
    return ResolvedCLIClient(
        name="claude",
        executable=["claude"],
        internal_args=["--print", "--output-format", "json"],
        config_args=["--permission-mode", "acceptEdits", "--model", "sonnet"],
        env={},
        timeout_seconds=30,
        parser="claude_json",
        runner="claude",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )


def _grok_client():
    role = _role()
    return ResolvedCLIClient(
        name="grok",
        executable=["grok"],
        internal_args=["--output-format", "json"],
        config_args=["--permission-mode", "auto"],
        env={},
        timeout_seconds=30,
        parser="grok_json",
        runner="grok",
        roles={"default": role},
        output_to_file=None,
        working_dir=None,
    )


def test_apply_model_override_noop_when_unset():
    agent = BaseCLIAgent(_claude_client_with_pinned_sonnet())
    cmd = ["claude", "--print", "--model", "sonnet"]
    assert agent._apply_model_override(cmd, None) == cmd


def test_apply_model_override_replaces_pinned_model():
    agent = BaseCLIAgent(_claude_client_with_pinned_sonnet())
    cmd = ["claude", "--print", "--permission-mode", "acceptEdits", "--model", "sonnet"]
    out = agent._apply_model_override(cmd, "fable")
    assert out == ["claude", "--print", "--permission-mode", "acceptEdits", "--model", "fable"]
    assert out.count("--model") == 1
    assert "sonnet" not in out


def test_apply_model_override_strips_short_flag():
    agent = BaseCLIAgent(_claude_client_with_pinned_sonnet())
    cmd = ["grok", "-m", "old-model", "--output-format", "json"]
    out = agent._apply_model_override(cmd, "grok-4")
    assert "-m" not in out
    assert out[-2:] == ["--model", "grok-4"]
    assert "old-model" not in out


def test_apply_model_override_adds_when_missing():
    agent = BaseCLIAgent(_claude_client_with_pinned_sonnet())
    cmd = ["gemini", "-o", "json", "--yolo"]
    out = agent._apply_model_override(cmd, "gemini-2.5-pro")
    assert out == ["gemini", "-o", "json", "--yolo", "--model", "gemini-2.5-pro"]


@pytest.mark.asyncio
async def test_claude_agent_model_override_before_prompt(monkeypatch):
    """Model flag lands among options; positional prompt stays last."""
    client = _claude_client_with_pinned_sonnet()
    agent = ClaudeAgent(client)
    role = client.get_role("default")
    captured: dict = {}

    class DummyProcess:
        returncode = 0

        async def communicate(self, input_data=None):
            payload = {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "result": "ok",
            }
            return json.dumps(payload).encode(), b""

    async def fake_create(*args, **_kwargs):
        captured["cmd"] = list(args)
        return DummyProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    result = await agent.run(
        role=role,
        prompt="do the thing",
        system_prompt=None,
        files=[],
        images=[],
        model="fable",
    )

    cmd = result.sanitized_command
    assert cmd[-1] == "do the thing"
    assert "--model" in cmd
    model_idx = cmd.index("--model")
    assert cmd[model_idx + 1] == "fable"
    assert "sonnet" not in cmd
    assert model_idx < len(cmd) - 1  # model flag before trailing prompt


def test_grok_apply_model_override_keeps_single_last():
    """Grok --single takes a prompt value; --model must not land after it."""
    agent = GrokAgent(_grok_client())
    role = _role()
    cmd = agent._build_command(role=role, system_prompt="sys")
    assert cmd[-1] == "--single"
    out = agent._apply_model_override(cmd, "grok-4.5")
    assert out[-1] == "--single"
    assert out[-3:] == ["--model", "grok-4.5", "--single"]
    assert out.count("--model") == 1


@pytest.mark.asyncio
async def test_grok_agent_model_override_before_single(monkeypatch):
    """Runtime model flag stays among options; --single <prompt> stays terminal."""
    client = _grok_client()
    agent = GrokAgent(client)
    role = client.get_role("default")
    captured: dict = {}

    class DummyProcess:
        returncode = 0

        async def communicate(self, input_data=None):
            payload = {"text": "ok", "stopReason": "EndTurn"}
            return json.dumps(payload).encode(), b""

    async def fake_create(*args, **_kwargs):
        captured["cmd"] = list(args)
        return DummyProcess()

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")

    result = await agent.run(
        role=role,
        prompt="do the thing",
        system_prompt=None,
        files=[],
        images=[],
        model="grok-4.5",
    )

    cmd = result.sanitized_command
    assert cmd[-2:] == ["--single", "do the thing"]
    model_idx = cmd.index("--model")
    single_idx = cmd.index("--single")
    assert cmd[model_idx + 1] == "grok-4.5"
    assert model_idx < single_idx


@pytest.mark.asyncio
async def test_clink_tool_forwards_model_to_agent(monkeypatch):
    """CLinkTool.execute passes request.model into agent.run."""
    from clink.agents import AgentOutput
    from clink.parsers.base import ParsedCLIResponse
    from tools.clink import CLinkTool

    seen: dict = {}

    class DummyAgent:
        async def run(self, **kwargs):
            seen.update(kwargs)
            return AgentOutput(
                parsed=ParsedCLIResponse(content="ok", metadata={"model_used": kwargs.get("model")}),
                sanitized_command=["claude", "--model", kwargs.get("model") or "sonnet"],
                returncode=0,
                stdout="{}",
                stderr="",
                duration_seconds=0.01,
                parser_name="claude_json",
            )

    monkeypatch.setattr("tools.clink.create_agent", lambda client: DummyAgent())

    tool = CLinkTool()
    results = await tool.execute(
        {
            "prompt": "review",
            "cli_name": "claude",
            "role": "default",
            "model": "fable",
            "absolute_file_paths": [],
            "images": [],
        }
    )
    assert seen.get("model") == "fable"
    assert len(results) == 1
