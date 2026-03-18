"""Tests for config loading."""

from pathlib import Path

from speks.core.config import ProjectConfig, load_config


class TestLoadConfig:
    def test_defaults_without_file(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path)
        assert cfg.project_name == "My Project"
        assert cfg.serve_port == 8000

    def test_reads_toml(self, tmp_path: Path) -> None:
        (tmp_path / "speks.toml").write_text(
            '[project]\nname = "Custom"\nserve_port = 9000\n',
            encoding="utf-8",
        )
        cfg = load_config(tmp_path)
        assert cfg.project_name == "Custom"
        assert cfg.serve_port == 9000
