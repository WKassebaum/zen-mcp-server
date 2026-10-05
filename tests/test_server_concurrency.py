"""Model calls run off the event loop, so the MCP server keeps serving: different tools run concurrently, while
calls of the same tool (one shared instance in server.TOOLS, holding per-run state) run one after the other."""

import asyncio
import json
import threading
import time
from unittest.mock import patch

import pytest

import server
from providers.gemini import GeminiModelProvider
from providers.registry import ModelProviderRegistry
from providers.shared import ModelResponse, ProviderType

MODEL = "gemini-3.8-flash"
OTHER_MODEL = "gemini-2.5-flash"
DELAY = 0.3  # each mocked model call blocks its thread this long


class SlowModel:
    """Stands in for GeminiModelProvider.generate_content: blocks its thread for DELAY seconds and records the call."""

    def __init__(self, replies=None):
        self.calls: list[dict] = []
        self._replies = list(replies or [])
        self._lock = threading.Lock()

    def __call__(self, **kwargs):
        start = time.monotonic()
        time.sleep(DELAY)
        with self._lock:
            content = self._replies.pop(0) if self._replies else "Considered answer."
            self.calls.append(
                {
                    "model": kwargs["model_name"],
                    "prompt": kwargs["prompt"],
                    "thread": threading.get_ident(),
                    "start": start,
                    "end": time.monotonic(),
                }
            )
        return ModelResponse(
            content=content,
            usage={},
            model_name=kwargs["model_name"],
            provider=ProviderType.GOOGLE,
            metadata={"finish_reason": "STOP"},
        )


@pytest.fixture(autouse=True)
def gemini_available(monkeypatch):
    # Earlier tests in the suite can leave the registry without a usable Gemini provider
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-tests")
    ModelProviderRegistry.reset_for_testing()
    ModelProviderRegistry.register_provider(ProviderType.GOOGLE, GeminiModelProvider)


def _slow(replies=None):
    model = SlowModel(replies)
    return model, patch.object(GeminiModelProvider, "generate_content", side_effect=model)


def _chat(tmp_path, prompt, model=MODEL):
    return {"prompt": prompt, "model": model, "working_directory_absolute_path": str(tmp_path)}


def _thinkdeep(model=MODEL):
    return {
        "step": "Think about the cache layout",
        "step_number": 1,
        "total_steps": 1,
        "next_step_required": False,
        "findings": "Keys hash the content.",
        "model": model,
    }


def _consensus(model=MODEL):
    return {
        "step": "Should we ship it?",
        "step_number": 1,
        "total_steps": 1,
        "next_step_required": False,
        "findings": "Looks ready.",
        # Consensus needs two models; step 1 consults only the first
        "models": [{"model": model, "stance": "for"}, {"model": model, "stance": "against"}],
    }


@pytest.mark.asyncio
async def test_different_tools_run_concurrently(tmp_path):
    model, patched = _slow()
    with patched:
        started = time.monotonic()
        await asyncio.gather(
            server.handle_call_tool("chat", _chat(tmp_path, "Say hi")),
            server.handle_call_tool("thinkdeep", _thinkdeep()),
        )
        elapsed = time.monotonic() - started
    assert len(model.calls) == 2
    first, second = sorted(model.calls, key=lambda call: call["start"])
    assert second["start"] < first["end"]  # the two model calls overlapped
    assert elapsed < 0.5, f"two {DELAY}s model calls of different tools took {elapsed:.2f}s"


@pytest.mark.asyncio
async def test_calls_of_one_tool_run_one_after_the_other(tmp_path):
    model, patched = _slow()
    with patched:
        started = time.monotonic()
        first, second = await asyncio.gather(
            server.handle_call_tool("chat", _chat(tmp_path, "First question", model=MODEL)),
            server.handle_call_tool("chat", _chat(tmp_path, "Second question", model=OTHER_MODEL)),
        )
        elapsed = time.monotonic() - started
    assert elapsed >= 2 * DELAY
    earlier, later = sorted(model.calls, key=lambda call: call["start"])
    assert later["start"] >= earlier["end"]  # no overlap
    # Each call used only its own model and prompt: the second saw nothing of the first.
    assert (earlier["model"], later["model"]) == (MODEL, OTHER_MODEL)
    assert "First question" in earlier["prompt"] and "Second question" not in earlier["prompt"]
    assert "Second question" in later["prompt"] and "First question" not in later["prompt"]
    assert json.loads(first[0].text)["metadata"]["model_used"] == MODEL
    assert json.loads(second[0].text)["metadata"]["model_used"] == OTHER_MODEL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "tool, arguments, replies, expected_calls",
    [
        ("chat", lambda tmp_path: _chat(tmp_path, "Say hi"), None, 1),
        ("chat", lambda tmp_path: _chat(tmp_path, "Say hi"), ["", "Second try."], 2),  # empty-response retry
        ("thinkdeep", lambda tmp_path: _thinkdeep(), None, 1),
        ("consensus", lambda tmp_path: _consensus(), None, 1),
    ],
    ids=["simple", "simple-retry", "workflow-expert", "consensus"],
)
async def test_every_model_call_runs_off_the_event_loop(tmp_path, tool, arguments, replies, expected_calls):
    model, patched = _slow(replies)
    with patched:
        await server.handle_call_tool(tool, arguments(tmp_path))
    assert len(model.calls) == expected_calls
    loop_thread = threading.get_ident()
    assert all(call["thread"] != loop_thread for call in model.calls)
