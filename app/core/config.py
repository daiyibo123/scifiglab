from pathlib import Path
from pydantic_settings import BaseSettings


BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"

DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    # ---- 基础 ----
    APP_NAME: str = "SciFigLab"
    APP_VERSION: str = "0.1.0"
    APP_ENV: str = "development"  # development / production

    # ---- 安全 ----
    SECRET_KEY: str = "change-me-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # ---- 数据库 ----
    DATABASE_URL: str = f"sqlite:///{DATA_DIR / 'researchexphub.db'}"

    # ---- SMTP 邮件 ----
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""
    SMTP_USE_TLS: bool = True

    # ---- 邮箱验证码策略 ----
    EMAIL_CODE_EXPIRE_MINUTES: int = 10
    EMAIL_CODE_RESEND_INTERVAL_SECONDS: int = 60
    EMAIL_CODE_MAX_PER_HOUR: int = 5

    # ---- 上传限制 ----
    UPLOAD_MAX_SIZE_MB: int = 20

    # ---- GitHub ----
    GITHUB_REPO_URL: str = "https://github.com/daiyibo123/scifiglab.git"

    # ---- 数据目录（只读，供外部引用）----
    DATA_DIR: str = str(DATA_DIR)

    @property
    def is_production(self) -> bool:
        return self.APP_ENV == "production"

    @property
    def debug(self) -> bool:
        return not self.is_production

    class Config:
        env_file = str(BASE_DIR / ".env")
        env_file_encoding = "utf-8"


settings = Settings()
