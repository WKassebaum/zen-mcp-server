"""File-list descriptions mention native media exactly for the tools that send files to a model."""

import pytest

from tools import (
    AnalyzeTool,
    ChatTool,
    CodeReviewTool,
    ConsensusTool,
    DebugIssueTool,
    DocgenTool,
    PrecommitTool,
    RefactorTool,
    SecauditTool,
    TestGenTool,
    ThinkDeepTool,
    TracerTool,
)
from tools.shared.base_models import MEDIA_FILES_NOTE

SENDS_FILES_TO_A_MODEL = [
    AnalyzeTool,
    CodeReviewTool,
    ConsensusTool,
    DebugIssueTool,
    PrecommitTool,
    RefactorTool,
    SecauditTool,
    TestGenTool,
    ThinkDeepTool,
]


def _description(tool, field):
    return tool.get_input_schema()["properties"][field]["description"]


@pytest.mark.parametrize("tool_cls", SENDS_FILES_TO_A_MODEL)
def test_workflow_tools_that_call_a_model_mention_media(tool_cls):
    assert _description(tool_cls(), "relevant_files").endswith(MEDIA_FILES_NOTE)


@pytest.mark.parametrize("tool_cls", [DocgenTool, TracerTool])
def test_tools_that_never_send_files_to_a_model_do_not(tool_cls):
    assert MEDIA_FILES_NOTE not in _description(tool_cls(), "relevant_files")


def test_chat_mentions_media():
    assert _description(ChatTool(), "absolute_file_paths").endswith(MEDIA_FILES_NOTE)
