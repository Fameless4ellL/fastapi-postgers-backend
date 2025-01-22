from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    bot_token: str = ""
    """private key for bot to able read passport Data"""
    bot_private_key: str = ""
    """url for web app page, usually for login page to call passport data"""
    web_app_url: str = "https://webhook.site/4f4f47fa-a71b-476d-ba89-298d23ba45ad"
    """Setup webhook for bot on this url"""
    bot_webhook: str = "https://webhook.site/4f4f47fa-a71b-476d-ba89-298d23ba45ad"
    """List of admins. it will create a list of admins who can access to admin panel"""
    admins: list[str] = ["zaurDzass"]
    """Able to see additional logs"""
    debug: bool = True
    database_url: str = "postgresql+asyncpg://postgres:postgres@db/postgres"


settings = Settings()
