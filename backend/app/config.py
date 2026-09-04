from pathlib import Path
import sys

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_NAME = "qwen3.5-9b-hauhau-aggressive-mxfp4"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_host: str = "127.0.0.1"
    app_port: int = 8787
    cors_origins: str = (
        "http://127.0.0.1:5173,http://localhost:5173,"
        "http://127.0.0.1:5174,http://localhost:5174,"
        "http://127.0.0.1:7777,http://localhost:7777,"
        "http://127.0.0.1:8787,http://localhost:8787,"
        "https://kiln.plainlist.space"
    )
    sqlite_path: str = str(ROOT / "data" / "chat.db")

    mlx_base_url: str = "http://127.0.0.1:8081"
    mlx_timeout_s: float = 600.0
    mlx_connect_timeout_s: float = 5.0

    model_name: str = DEFAULT_MODEL_NAME
    model_path: str = ""
    model_library_path: str = str(ROOT.parent / "models")
    model_selection_state_path: str = str(ROOT / "data" / "active-model.json")
    model_switch_enabled: bool = sys.platform == "darwin"
    model_downloads_enabled: bool = sys.platform == "darwin"
    model_switch_script: str = str(ROOT / "scripts" / "activate-model.sh")

    media_python: str = str(ROOT.parent / ".media-venv" / "bin" / "python")
    image_flux_dir: str = str(ROOT.parent / "image-flux2-klein-4b-mflux-4bit")
    image_zimage_dir: str = str(ROOT.parent / "image-z-image-turbo-mflux-4bit")
    video_wan_aux_dir: str = str(ROOT.parent / "video-wan21-t2v-1.3b-aux")
    video_wan_dit: str = str(ROOT.parent / "video-nsfw-wan-1.3b" / "wan_1.3B_exp_e14.safetensors")
    video_wan_mlx_dir: str = str(ROOT.parent / "video-nsfw-wan-1.3b-mlx")
    generations_dir: str = str(ROOT / "data" / "generations")
    mlx_launch_label: str = "gui/{uid}/com.kiln.mlx"
    mlx_plist: str = str(Path.home() / "Library" / "LaunchAgents" / "com.kiln.mlx.plist")
    pause_chat_for_image: bool = False
    pause_chat_for_video: bool = True
    default_image_backend: str = "z-image-turbo"
    default_video_backend: str = "nsfw-wan-1.3b"
    video_teacache_threshold: float = 0.05

    context_window: int = 262144
    # Prompt-only. Do not subtract max_tokens from this (Qwen3.5-9B hybrid KV is ~1GB @ 32k).
    practical_prompt_budget: int = 32768
    default_max_tokens: int = 8192
    max_tokens_cap: int = 32768
    default_temperature: float = 1.0
    default_top_p: float = 0.95
    default_top_k: int = 20
    default_system: str = ""
    enable_thinking: bool = True
    reasoning_effort: str = "medium"
    thinking_budget_low: int = 256
    thinking_budget_medium: int = 1024
    thinking_budget_xhigh: int = 0
    preserve_thinking: bool = False
    overflow_policy: str = "truncate_oldest"
    heartbeat_s: float = 15.0
    generation_concurrency: int = 1
    bootstrap_username: str = ""
    bootstrap_password: str = ""
    auth_signup: bool = False
    cookie_secure: bool = False
    trust_proxy_headers: bool = False
    session_days: int = 14
    chat_per_minute: int = 20
    login_per_minute: int = 5
    max_request_bytes: int = 12_582_912
    max_message_chars: int = 8_000_000

    def cors_origin_list(self) -> list[str]:
        return [x.strip() for x in self.cors_origins.split(",") if x.strip()]

    def mlx_chat_url(self) -> str:
        base = self.mlx_base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def mlx_health_url(self) -> str:
        base = self.mlx_base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base[:-3]}/health"
        return f"{base}/health"

    def mlx_completions_url(self) -> str:
        base = self.mlx_base_url.rstrip("/")
        if base.endswith("/v1"):
            return f"{base}/completions"
        return f"{base}/v1/completions"


settings = Settings()
