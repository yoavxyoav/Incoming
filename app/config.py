from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Alert filtering
    region: str = "*"
    include_test_alerts: bool = False

    # Polling
    poll_interval: float = 1.0
    clear_grace_polls: int = 3

    # History / grouping
    max_history: int = 50
    max_groups: int = 50
    group_window_seconds: int = 60
    all_clear_display_seconds: int = 300


    # Optional MQTT (disabled when host is empty)
    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_user: str = ""
    mqtt_pass: str = ""
    mqtt_topic: str = "/redalert"

    # Optional Apprise notifications (space-separated URLs)
    notifiers: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"
    debug_mode: bool = False

    # Geographic data
    lamas_path: str = "data/lamas.json"
    lamas_url: str = "https://raw.githubusercontent.com/t0mer/Redalert/master/lamas.json"


settings = Settings()
