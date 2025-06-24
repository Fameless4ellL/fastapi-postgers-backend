from pydantic_settings import BaseSettings, SettingsConfigDict


class Email(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='EMAIL_')

    FROM: str = "string"
    host: str = ""
    port: int = 587
    login: str = ""
    password: str = ""


class Settings(BaseSettings):
    bot_token: str = "7112641937:AAEF_RgG6s4_gpiQW7PWTzxImH0CIH3lyeg"
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
    """Secret key for JWT token"""
    jwt_secret: str = "thisisatest"
    """Cron key for cron jobs"""
    cron_key: str = "thisisatest"
    back_url: str = "http://localhost:8100"

    """Main Address"""
    address: str = "0xf2167f01Cd7759C33B787f0e0be1E422348F8617"
    """Main Private Key"""
    private_key: str = "54c302fd650d7cbb6afb8b4644a79fbb3a1177e8502d6c1b2365c8cbb97c468a"

    """2FA"""
    twofa_secret: str = "xA1BajGnTjd8yhXIIfvtzKBGvtim7NFJsSYjH5ZL"

    """DB settings"""
    postgres_user: str = "postgres"
    postgres_password: str = "postgres"
    database_url: str = "postgresql+{mode}://{user}:{password}@{database}/postgres"


class Minio(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='MINIO_')

    endpoint: str = "localhost:9000"
    secure: bool = False
    access_key: str = "AKIA3RYC6GBNMSHQQLBB"
    secret_key: str = "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"


class AWS(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='AWS_')

    access_key: str = "AKIA3RYC6GBNMSHQQLBB"
    secret_key: str = "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"
    region: str = "us-east-1"
    minio: Minio = Minio()


aws = AWS()
email = Email()
settings = Settings()
