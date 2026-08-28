from __future__ import annotations

from pathlib import Path

import novel_api.cli as cli


def _capture_main(monkeypatch: object, argv: list[str]) -> dict[str, object]:
    captured: dict[str, object] = {}

    def fake_create_app(settings: object) -> object:
        captured["settings"] = settings
        return object()

    def fake_run(app: object, **kwargs: object) -> None:
        captured["app"] = app
        captured["kwargs"] = kwargs

    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setattr(cli.uvicorn, "run", fake_run)

    cli.main(argv)
    return captured


def test_main_uses_default_bindings_and_checkout_data_root(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("NOVEL_DATA_ROOT", raising=False)
    monkeypatch.delenv("NOVEL_API_HOST", raising=False)
    monkeypatch.delenv("NOVEL_API_PORT", raising=False)
    monkeypatch.delenv("NOVEL_DEV_CORS_ORIGIN", raising=False)
    monkeypatch.delenv("NOVEL_WEBUI_DIST", raising=False)
    monkeypatch.chdir(tmp_path)

    captured = _capture_main(monkeypatch, [])
    settings = captured["settings"]

    assert settings.host == "0.0.0.0"
    assert settings.port == 8765
    assert settings.data_root == Path(__file__).resolve().parents[2] / "data"
    assert settings.dev_cors_origin is None
    assert settings.webui_dist is None
    assert captured["kwargs"] == {"host": "0.0.0.0", "port": 8765}


def test_main_prefers_cli_over_environment(monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_ROOT", r"C:\tmp\env-data")
    monkeypatch.setenv("NOVEL_API_HOST", "192.0.2.10")
    monkeypatch.setenv("NOVEL_API_PORT", "9010")
    monkeypatch.setenv("NOVEL_DEV_CORS_ORIGIN", "https://env.example")
    monkeypatch.setenv("NOVEL_WEBUI_DIST", r"C:\tmp\env-webui")

    captured = _capture_main(
        monkeypatch,
        [
            "--data-root",
            r"C:\tmp\cli-data",
            "--host",
            "127.0.0.1",
            "--port",
            "9001",
            "--dev-cors-origin",
            "https://cli.example",
            "--webui-dist",
            r"C:\tmp\cli-webui",
        ],
    )
    settings = captured["settings"]

    assert settings.data_root == Path(r"C:\tmp\cli-data")
    assert settings.host == "127.0.0.1"
    assert settings.port == 9001
    assert settings.dev_cors_origin == "https://cli.example"
    assert settings.webui_dist == Path(r"C:\tmp\cli-webui")
    assert captured["kwargs"] == {"host": "127.0.0.1", "port": 9001}


def test_main_uses_environment_values_when_cli_is_absent(monkeypatch) -> None:
    monkeypatch.setenv("NOVEL_DATA_ROOT", r"C:\tmp\env-data")
    monkeypatch.setenv("NOVEL_API_HOST", "192.0.2.20")
    monkeypatch.setenv("NOVEL_API_PORT", "9020")
    monkeypatch.setenv("NOVEL_DEV_CORS_ORIGIN", "https://env.example")
    monkeypatch.setenv("NOVEL_WEBUI_DIST", r"C:\tmp\env-webui")

    captured = _capture_main(monkeypatch, [])
    settings = captured["settings"]

    assert settings.data_root == Path(r"C:\tmp\env-data")
    assert settings.host == "192.0.2.20"
    assert settings.port == 9020
    assert settings.dev_cors_origin == "https://env.example"
    assert settings.webui_dist == Path(r"C:\tmp\env-webui")
    assert captured["kwargs"] == {"host": "192.0.2.20", "port": 9020}
