"""配置读取测试。"""

from pathlib import Path

from app.config import get_doubao_settings, load_dotenv


def test_load_dotenv_does_not_override_existing_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DOUBAO_API_KEY=from_file\nDOUBAO_MODEL=file_model\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOUBAO_API_KEY", "from_env")
    load_dotenv(env_file)
    assert get_doubao_settings().api_key == "from_env"


def test_load_dotenv_reads_local_values(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "\n".join(
            [
                "DOUBAO_API_KEY=test_key",
                "DOUBAO_BASE_URL=https://example.test/api/v3",
                "DOUBAO_MODEL=test_model",
                "DOUBAO_TIMEOUT_SECONDS=12.5",
            ]
        ),
        encoding="utf-8",
    )
    for key in (
        "DOUBAO_API_KEY",
        "DOUBAO_BASE_URL",
        "DOUBAO_MODEL",
        "DOUBAO_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(key, raising=False)
    load_dotenv(env_file)
    settings = get_doubao_settings()
    assert settings.api_key == "test_key"
    assert settings.base_url == "https://example.test/api/v3"
    assert settings.model == "test_model"
    assert settings.timeout_seconds == 12.5
    assert settings.is_configured


def test_placeholder_settings_are_not_configured(monkeypatch):
    monkeypatch.setenv("DOUBAO_API_KEY", "your_ark_api_key_here")
    monkeypatch.setenv("DOUBAO_MODEL", "your_doubao_endpoint_or_model_id_here")
    settings = get_doubao_settings()
    assert not settings.is_configured
