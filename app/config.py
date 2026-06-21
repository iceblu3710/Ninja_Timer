"""Configuration module for loading settings from YAML"""
import os
from pathlib import Path

import yaml


class Settings:
    """Application settings loaded from YAML config file"""

    def __init__(self):
        self.config_path = self._get_config_path()
        self._load_config()

    def _get_config_path(self) -> Path:
        """Get the path to settings.yaml, preferring config/ directory"""
        possible_paths = [
            Path("config/settings.yaml"),
            Path("./config/settings.yaml"),
            Path.cwd() / "config" / "settings.yaml",
        ]

        for path in possible_paths:
            if path.exists():
                return path

        return Path("config/settings.yaml")

    def _load_config(self) -> None:
        """Load configuration from YAML file"""
        self.app_name = "Dynasty Ninja Timer"
        self.app_version = "0.1.0"
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.host = "0.0.0.0"
        self.port = int(os.getenv("PORT", "8000"))
        self.reload = os.getenv("RELOAD", "true").lower() == "true"

        self.database_url = "sqlite:///./data/dynasty_ninja_timer.sqlite"
        self.database_echo = self.debug

        self.hardware_driver = "simulated"
        self.countdown_seconds = 3
        self.default_mode = "open_gym"

        try:
            if self.config_path.exists():
                with open(self.config_path, "r") as f:
                    config = yaml.safe_load(f) or {}
                    self._merge_config(config)
        except Exception as e:
            if self.debug:
                raise
            print(f"Warning: Could not load config file: {e}")

    def _merge_config(self, config: dict) -> None:
        """Merge YAML config into settings"""
        app_config = config.get("app", {})
        self.app_name = app_config.get("name", self.app_name)
        self.app_version = app_config.get("version", self.app_version)
        self.debug = app_config.get("debug", self.debug)
        self.host = app_config.get("host", self.host)
        self.port = app_config.get("port", self.port)

        db_config = config.get("database", {})
        self.database_url = db_config.get("url", self.database_url)
        self.database_echo = db_config.get("echo", self.database_echo)

        hw_config = config.get("hardware", {})
        self.hardware_driver = hw_config.get("driver", self.hardware_driver)
        self.countdown_seconds = hw_config.get("countdown_seconds", self.countdown_seconds)
        self.default_mode = hw_config.get("default_mode", self.default_mode)

    def to_dict(self) -> dict:
        """Convert settings to dictionary for API responses"""
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "debug": self.debug,
            "hardware_driver": self.hardware_driver,
            "countdown_seconds": self.countdown_seconds,
            "default_mode": self.default_mode,
        }


def get_settings() -> Settings:
    """Get singleton settings instance"""
    if not hasattr(get_settings, "_instance"):
        get_settings._instance = Settings()
    return get_settings._instance
