from pathlib import Path
from unittest.mock import patch

from magi.config import apply_config, load_config
from magi.core import DEFAULT_MODELS


class TestLoadConfig:
    def test_missing_file_returns_empty(self):
        with patch("magi.config.CONFIG_PATH", Path("/nonexistent/config.toml")):
            assert load_config() == {}

    def test_valid_toml_loads(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[models]\nmelchior = "qwen3:8b"\n')
        with patch("magi.config.CONFIG_PATH", cfg_file):
            cfg = load_config()
            assert cfg["models"]["melchior"] == "qwen3:8b"


class TestApplyConfig:
    def test_cli_overrides_config(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[models]\nmelchior = "qwen3:8b"\n')
        with patch("magi.config.CONFIG_PATH", cfg_file):
            models = dict(DEFAULT_MODELS)
            models, invited = apply_config(models, {"melchior": "llama3.1:8b", "balthasar": None, "casper": None})
            assert models["MELCHIOR"] == "llama3.1:8b"

    def test_config_overrides_defaults(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[models]\nbalthasar = "hermes3:8b"\n')
        with patch("magi.config.CONFIG_PATH", cfg_file):
            models = dict(DEFAULT_MODELS)
            models, invited = apply_config(models, {"melchior": None, "balthasar": None, "casper": None})
            assert models["BALTHASAR"] == "hermes3:8b"
            assert models["MELCHIOR"] == DEFAULT_MODELS["MELCHIOR"]

    def test_auto_invite_specialists(self, tmp_path):
        cfg_file = tmp_path / "config.toml"
        cfg_file.write_text('[specialists]\ninvite = ["banker"]\n')
        with patch("magi.config.CONFIG_PATH", cfg_file):
            models = dict(DEFAULT_MODELS)
            models, invited = apply_config(models, {"melchior": None, "balthasar": None, "casper": None})
            assert "BANKER" in models
            assert "BANKER" in invited

    def test_no_config_file(self):
        with patch("magi.config.CONFIG_PATH", Path("/nonexistent/config.toml")):
            models = dict(DEFAULT_MODELS)
            models, invited = apply_config(models, {"melchior": None, "balthasar": None, "casper": None})
            assert models == DEFAULT_MODELS
            assert invited == []


class TestMaxRounds:
    def test_default_when_unset(self, tmp_path, monkeypatch):
        import magi.config as config

        monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "nope.toml")
        assert config.max_rounds(2) == 2

    def test_read_from_config(self, tmp_path, monkeypatch):
        import magi.config as config

        path = tmp_path / "config.toml"
        path.write_text("[options]\nmax_rounds = 4\n")
        monkeypatch.setattr(config, "CONFIG_PATH", path)
        assert config.max_rounds(2) == 4

    def test_clamped_to_something_sane(self, tmp_path, monkeypatch):
        import magi.config as config

        path = tmp_path / "config.toml"
        path.write_text("[options]\nmax_rounds = 99\n")
        monkeypatch.setattr(config, "CONFIG_PATH", path)
        assert config.max_rounds(2) == 6

        path.write_text("[options]\nmax_rounds = 0\n")
        assert config.max_rounds(2) == 1

    def test_garbage_falls_back(self, tmp_path, monkeypatch):
        import magi.config as config

        path = tmp_path / "config.toml"
        path.write_text('[options]\nmax_rounds = "lots"\n')
        monkeypatch.setattr(config, "CONFIG_PATH", path)
        assert config.max_rounds(2) == 2
