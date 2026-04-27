from syncore_cli.config import load_config


def test_config_reads_syncore_api_url(monkeypatch) -> None:
    monkeypatch.setenv("SYNCORE_API_URL", "http://localhost:9000")
    config = load_config()
    assert config.api_url == "http://localhost:9000"
