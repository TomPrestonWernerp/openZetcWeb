import sys


def test_import_openzetc_does_not_eagerly_import_knowledge(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    sys.modules.pop("openzetc", None)
    sys.modules.pop("openzetc.knowledge", None)

    import openzetc

    assert openzetc.get_version() == openzetc.__version__
    assert "openzetc.knowledge" not in sys.modules
