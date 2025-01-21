from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str = ""
    bot_private_key: str = ""
    platform_url: str = ""


settings = Settings()
