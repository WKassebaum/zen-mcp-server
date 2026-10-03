"""A new workflow run starts clean: nothing from the previous run on the same tool instance reaches its expert call.

Tool instances are shared across calls (server.TOOLS), and tools record per-run configuration in
customize_workflow_response, which runs after the expert call. Without a reset, a single-step run's expert
prompt shows the previous run's files and options.
"""

from unittest.mock import patch

import pytest

from providers.gemini import GeminiModelProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ModelResponse, ProviderType
from tools.analyze import AnalyzeTool
from tools.codereview import CodeReviewTool
from tools.debug import DebugIssueTool
from tools.precommit import PrecommitTool
from tools.refactor import RefactorTool
from tools.secaudit import SecauditTool
from tools.thinkdeep import ThinkDeepTool
from utils.model_context import ModelContext

MODEL = "gemini-3.8-flash"


@pytest.fixture(autouse=True)
def gemini_available(monkeypatch):
    # Earlier tests in the suite can leave the registry without a usable Gemini provider
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-tests")
    ModelProviderRegistry.reset_for_testing()
    ModelProviderRegistry.register_provider(ProviderType.GOOGLE, GeminiModelProvider)


def _reply():
    return ModelResponse(content='{"status": "complete"}', usage={}, model_name=MODEL, provider=ProviderType.GOOGLE)


def _single_step(**fields):
    return {
        "step": "Review the code",
        "step_number": 1,
        "total_steps": 1,
        "next_step_required": False,
        "findings": "Nothing unusual yet.",
        "model": MODEL,
        "_model_context": ModelContext(MODEL),
        "_resolved_model_name": MODEL,
        **fields,
    }


def _source(directory, name):
    path = directory / name
    path.write_text("def answer():\n    return 42\n")
    return str(path)


def _files_run(path):
    return {"relevant_files": [path]}


def _precommit_run(path):
    return {"path": str(path.rsplit("/", 1)[0]), "relevant_files": [path]}


def _secaudit_run(path):
    return {"relevant_files": [path], "security_scope": "Internal web service"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool_class, run_fields",
    [
        (AnalyzeTool, _files_run),
        (CodeReviewTool, _files_run),
        (RefactorTool, _files_run),
        (PrecommitTool, _precommit_run),
        (SecauditTool, _secaudit_run),
    ],
)
async def test_second_run_expert_prompt_has_no_trace_of_the_first_run(tool_class, run_fields, tmp_path):
    first_dir = tmp_path / "first-run-repo"
    second_dir = tmp_path / "second-run-repo"
    first_dir.mkdir()
    second_dir.mkdir()
    tool = tool_class()

    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply()):
        await tool.execute(_single_step(**run_fields(_source(first_dir, "first_module.py"))))

    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply()) as generate:
        await tool.execute(_single_step(**run_fields(_source(second_dir, "second_module.py"))))

    prompt = generate.call_args.kwargs["prompt"]
    assert "second_module.py" in prompt
    assert "first-run-repo" not in prompt
    assert "first_module.py" not in prompt


@pytest.mark.asyncio
async def test_second_thinkdeep_run_uses_its_own_temperature(tmp_path):
    tool = ThinkDeepTool()
    source = _source(tmp_path, "module.py")

    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply()):
        await tool.execute(_single_step(relevant_files=[source], temperature=0.2))

    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply()) as generate:
        await tool.execute(_single_step(relevant_files=[source], temperature=0.9))

    assert generate.call_args.kwargs["temperature"] == 0.9


@pytest.mark.asyncio
async def test_second_debug_run_describes_its_own_issue(tmp_path):
    tool = DebugIssueTool()
    source = _source(tmp_path, "module.py")

    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply()):
        await tool.execute(_single_step(step="Login hangs after FIRST-ISSUE-TIMEOUT", relevant_files=[source]))

    with patch.object(GeminiModelProvider, "generate_content", return_value=_reply()) as generate:
        await tool.execute(_single_step(step="Export drops the last row", relevant_files=[source]))

    prompt = generate.call_args.kwargs["prompt"]
    assert "Export drops the last row" in prompt
    assert "FIRST-ISSUE-TIMEOUT" not in prompt
