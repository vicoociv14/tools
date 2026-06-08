import pytest

from lma.brain.qa import build_client, build_messages, resolve_question, extract_drawio, PRESETS
from lma.brain.state import Segment, Transcript


def _t():
    t = Transcript()
    t.add(Segment(0.0, 1.0, "wir nehmen Variante C", "You", "mic"))
    t.add(Segment(1.0, 2.0, "ok, einverstanden", "Remote", "system"))
    return t


def test_resolve_question_maps_presets():
    assert resolve_question("summary") == PRESETS["summary"]
    assert resolve_question("Decisions") == PRESETS["decisions"]
    assert resolve_question("was haben wir entschieden?") == "was haben wir entschieden?"


def test_build_messages_has_cacheable_transcript_block():
    system, user_text = build_messages(_t(), "summary")
    assert len(system) == 2
    assert system[1]["cache_control"] == {"type": "ephemeral"}
    assert "Variante C" in system[1]["text"]
    assert "[You]" in system[1]["text"] and "[Remote]" in system[1]["text"]
    assert user_text == PRESETS["summary"]


def test_build_messages_empty_transcript():
    system, user_text = build_messages(Transcript(), "hi")
    assert "(no transcript yet)" in system[1]["text"]
    assert user_text == "hi"


def test_extract_drawio_finds_mxgraph_block():
    ans = "Here you go:\n```xml\n<mxGraphModel><root/></mxGraphModel>\n```\nDone."
    block = extract_drawio(ans)
    assert block is not None and block.startswith("<mxGraphModel")


def test_extract_drawio_none_when_absent():
    assert extract_drawio("just some prose, no diagram") is None


def test_build_client_foundry_uses_base_url_and_model(monkeypatch):
    monkeypatch.setenv("LMA_FOUNDRY_API_KEY", "test-key")
    cfg = {
        "qa_backend": "foundry",
        "foundry_base_url": "https://res.services.ai.azure.com/anthropic",
        "foundry_model": "claude-sonnet-4-6",
    }
    client, model = build_client(cfg)
    assert model == "claude-sonnet-4-6"
    assert "res.services.ai.azure.com" in str(client.base_url)


def test_build_client_foundry_requires_key(monkeypatch):
    monkeypatch.delenv("LMA_FOUNDRY_API_KEY", raising=False)
    cfg = {"qa_backend": "foundry", "foundry_base_url": "https://res/anthropic"}
    with pytest.raises(RuntimeError):
        build_client(cfg)
