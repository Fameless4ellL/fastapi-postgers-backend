from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str = ""
    bot_private_key: str = ""
    web_app_url: str = "https://webhook.site/4f4f47fa-a71b-476d-ba89-298d23ba45ad"
    bot_webhook: str = "https://webhook.site/4f4f47fa-a71b-476d-ba89-298d23ba45ad"
    admins: list[str] = ["zaurDzass"]
    debug: bool = True
    database_url: str = "postgresql+asyncpg://postgres:postgres@db/postgres"


settings = Settings()
