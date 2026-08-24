from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from openzetc.utils import guard as guard_module


@pytest.mark.unit
def test_content_guard_defers_model_selection_until_first_llm_check(monkeypatch, tmp_path):
    keywords_file = tmp_path / "keywords.txt"
    keywords_file.write_text("blocked\n", encoding="utf-8")
    monkeypatch.setattr(guard_module.config, "enable_content_guard_llm", True)
    monkeypatch.setattr(guard_module.config, "content_guard_llm_model", "provider:model")

    selected_model = SimpleNamespace(call=AsyncMock(return_value=SimpleNamespace(content="合规")))
    select_model = MagicMock(return_value=selected_model)
    monkeypatch.setattr(guard_module, "select_model", select_model)

    content_guard = guard_module.ContentGuard(str(keywords_file))

    assert content_guard.llm_model is None
    select_model.assert_not_called()


@pytest.mark.unit
async def test_content_guard_loads_model_lazily_and_reuses_it(monkeypatch, tmp_path):
    keywords_file = tmp_path / "keywords.txt"
    keywords_file.write_text("blocked\n", encoding="utf-8")
    monkeypatch.setattr(guard_module.config, "enable_content_guard_llm", True)
    monkeypatch.setattr(guard_module.config, "content_guard_llm_model", "provider:model")

    selected_model = SimpleNamespace(call=AsyncMock(return_value=SimpleNamespace(content="合规")))
    select_model = MagicMock(return_value=selected_model)
    monkeypatch.setattr(guard_module, "select_model", select_model)

    content_guard = guard_module.ContentGuard(str(keywords_file))

    assert await content_guard.check("first request") is False
    assert await content_guard.check("second request") is False
    select_model.assert_called_once_with(model_spec="provider:model")
    assert selected_model.call.await_count == 2
