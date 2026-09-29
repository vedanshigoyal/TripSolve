from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://tripsolve:tripsolve@localhost:5433/tripsolve"

    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440

    osrm_url: str = "https://router.project-osrm.org"
    osrm_profile: str = "driving"
    osrm_timeout_seconds: float = 8.0
    # OSRM returns free-flow driving times; Jaipur's old city is slower than that,
    # and every stop costs a few minutes of parking / finding a ride.
    traffic_factor: float = 1.3
    leg_overhead_minutes: int = 5

    groq_api_key: str = ""
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-120b"
    llm_timeout_seconds: float = 20.0
    # For reasoning models; set LLM_REASONING_EFFORT= (empty) for models that reject the field.
    llm_reasoning_effort: str = "low"
    llm_reasoning_headroom_tokens: int = 1024

    solver_time_limit_seconds: float = 2.0
    cors_origins: str = "http://localhost:3000"

    @property
    def llm_enabled(self) -> bool:
        return bool(self.groq_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
