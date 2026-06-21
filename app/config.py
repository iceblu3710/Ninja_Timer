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
        self.app_version = "1.0.0"
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.host = "0.0.0.0"
        self.port = int(os.getenv("PORT", "8000"))
        self.scoreboard_port = int(os.getenv("SCOREBOARD_PORT", "8001"))
        self.kiosk_port = int(os.getenv("KIOSK_PORT", "8002"))
        self.reload = os.getenv("RELOAD", "true").lower() == "true"

        self.database_url = "sqlite:///./data/dynasty_ninja_timer.sqlite"
        self.database_echo = self.debug

        self.hardware_driver = "simulated"
        self.hardware_debounce_ms = int(os.getenv("HARDWARE_DEBOUNCE_MS", "250"))
        self.hardware_serial_port = os.getenv("HARDWARE_SERIAL_PORT")
        self.hardware_serial_baud = int(os.getenv("HARDWARE_SERIAL_BAUD", "115200"))
        self.hardware_heartbeat_timeout_seconds = int(
            os.getenv("HARDWARE_HEARTBEAT_TIMEOUT_SECONDS", "5")
        )
        self.hardware_reconnect_interval_seconds = int(
            os.getenv("HARDWARE_RECONNECT_INTERVAL_SECONDS", "2")
        )
        self.hardware_m5_host = os.getenv("HARDWARE_M5_HOST")
        self.hardware_mqtt_host = os.getenv("HARDWARE_MQTT_HOST")
        self.hardware_mqtt_port = int(os.getenv("HARDWARE_MQTT_PORT", "1883"))
        self.hardware_mqtt_topic_prefix = os.getenv(
            "HARDWARE_MQTT_TOPIC_PREFIX", "dynasty/timer/io"
        )
        self.hardware_mqtt_device_id = os.getenv("HARDWARE_MQTT_DEVICE_ID", "m5stamp-main")
        self.hardware_mqtt_username = os.getenv("HARDWARE_MQTT_USERNAME")
        self.hardware_mqtt_password = os.getenv("HARDWARE_MQTT_PASSWORD")
        self.countdown_seconds = 3
        self.default_mode = "open_gym"
        self.admin_pin = os.getenv("ADMIN_PIN", "1234")
        self.admin_token_secret = os.getenv("ADMIN_TOKEN_SECRET")
        self.admin_session_seconds = int(os.getenv("ADMIN_SESSION_SECONDS", "43200"))
        self.backup_retention_days = int(os.getenv("BACKUP_RETENTION_DAYS", "30"))

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
        self.scoreboard_port = app_config.get("scoreboard_port", self.scoreboard_port)
        self.kiosk_port = app_config.get("kiosk_port", self.kiosk_port)

        db_config = config.get("database", {})
        self.database_url = db_config.get("url", self.database_url)
        self.database_echo = db_config.get("echo", self.database_echo)

        hw_config = config.get("hardware", {})
        self.hardware_driver = hw_config.get("driver", self.hardware_driver)
        self.hardware_debounce_ms = int(hw_config.get("debounce_ms", self.hardware_debounce_ms))
        self.hardware_serial_port = hw_config.get("serial_port", self.hardware_serial_port)
        self.hardware_serial_baud = int(hw_config.get("serial_baud", self.hardware_serial_baud))
        self.hardware_heartbeat_timeout_seconds = int(
            hw_config.get("heartbeat_timeout_seconds", self.hardware_heartbeat_timeout_seconds)
        )
        self.hardware_reconnect_interval_seconds = int(
            hw_config.get("reconnect_interval_seconds", self.hardware_reconnect_interval_seconds)
        )
        self.hardware_m5_host = hw_config.get("m5_host", self.hardware_m5_host)
        self.hardware_mqtt_host = hw_config.get("mqtt_host", self.hardware_mqtt_host)
        self.hardware_mqtt_port = int(hw_config.get("mqtt_port", self.hardware_mqtt_port))
        self.hardware_mqtt_topic_prefix = hw_config.get(
            "mqtt_topic_prefix", self.hardware_mqtt_topic_prefix
        )
        self.hardware_mqtt_device_id = hw_config.get("mqtt_device_id", self.hardware_mqtt_device_id)
        self.hardware_mqtt_username = hw_config.get("mqtt_username", self.hardware_mqtt_username)
        self.hardware_mqtt_password = hw_config.get("mqtt_password", self.hardware_mqtt_password)
        self.countdown_seconds = hw_config.get("countdown_seconds", self.countdown_seconds)
        self.default_mode = hw_config.get("default_mode", self.default_mode)

        security_config = config.get("security", {})
        self.admin_pin = str(security_config.get("admin_pin", self.admin_pin))
        self.admin_token_secret = security_config.get(
            "admin_token_secret",
            self.admin_token_secret,
        )
        self.admin_session_seconds = int(
            security_config.get("admin_session_seconds", self.admin_session_seconds)
        )

        ops_config = config.get("operations", {})
        self.backup_retention_days = int(
            ops_config.get("backup_retention_days", self.backup_retention_days)
        )

    def to_dict(self) -> dict:
        """Convert settings to dictionary for API responses"""
        return {
            "app_name": self.app_name,
            "app_version": self.app_version,
            "debug": self.debug,
            "scoreboard_port": self.scoreboard_port,
            "kiosk_port": self.kiosk_port,
            "hardware_driver": self.hardware_driver,
            "hardware_debounce_ms": self.hardware_debounce_ms,
            "hardware_serial_port": self.hardware_serial_port,
            "hardware_serial_baud": self.hardware_serial_baud,
            "hardware_heartbeat_timeout_seconds": self.hardware_heartbeat_timeout_seconds,
            "hardware_reconnect_interval_seconds": self.hardware_reconnect_interval_seconds,
            "hardware_m5_host": self.hardware_m5_host,
            "hardware_mqtt_host": self.hardware_mqtt_host,
            "hardware_mqtt_port": self.hardware_mqtt_port,
            "hardware_mqtt_topic_prefix": self.hardware_mqtt_topic_prefix,
            "hardware_mqtt_device_id": self.hardware_mqtt_device_id,
            "countdown_seconds": self.countdown_seconds,
            "default_mode": self.default_mode,
            "admin_session_seconds": self.admin_session_seconds,
            "backup_retention_days": self.backup_retention_days,
        }


def get_settings() -> Settings:
    """Get singleton settings instance"""
    if not hasattr(get_settings, "_instance"):
        get_settings._instance = Settings()
    return get_settings._instance
