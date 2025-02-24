from pydantic_settings import BaseSettings


class Email(BaseSettings):
    _from: str = "string"
    host: str = ""
    port: int = 587
    login: str = ""
    password: str = ""


class Settings(BaseSettings):
    bot_token: str = ""
    """private key for bot to able read passport Data"""
    bot_private_key: str = ""
    """url for web app page, usually for login page to call passport data"""
    web_app_url: str = "https://84.201.170.185:3000"
    """Setup webhook for bot on this url"""
    bot_webhook: str = "https://webhook.site/0207e46f-f249-4ef0-989e-98f73987300f"
    """List of admins. it will create a list of admins who can access to admin panel"""
    admins: list[str] = ["zaurDzass"]
    """Able to see additional logs"""
    debug: bool = True
    database_url: str = "postgresql+{mode}://postgres:postgres@db/postgres"
    """Secret key for JWT token"""
    jwt_secret: str = "thisisatest"
    """Cron key for cron jobs"""
    cron_key: str = "thisisatest"
    back_url: str = "http://localhost:8100"

    """Main Address"""
    address: str = "0xf2167f01Cd7759C33B787f0e0be1E422348F8617"
    """Main Private Key"""
    private_key: str = "54c302fd650d7cbb6afb8b4644a79fbb3a1177e8502d6c1b2365c8cbb97c468a"


class AWS(BaseSettings):
    access_key: str = ""
    secret_key: str = ""
    region: str = "us-west-2"


aws = AWS()
email = Email()
settings = Settings()
