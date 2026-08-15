"""Configuration loader for 1TamilVT-TG."""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Bot configuration."""
    TOKEN: str = os.getenv("TOKEN", "")
    CHANNEL_ID: int = int(os.getenv("CHANNEL_ID", "0"))
    CHANNEL_USERNAME: str = os.getenv("CHANNEL_USERNAME", "").lstrip("@")
    TAMILMV_URL: str = os.getenv("TAMILMV_URL", "https://www.1tamilmv.fi")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    PORT: int = int(os.getenv("PORT", "8080"))
    SCRAPE_INTERVAL: int = int(os.getenv("SCRAPE_INTERVAL", "300"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Fallback proxy list for 1TamilMV domains
    PROXY_DOMAINS: list = [
        "https://www.1tamilmv.ing",
        "https://www.1tamilmv.fi",
        "https://www.1tamilmv.dad",
        "https://www.1tamilmv.in",
        "https://www.1tamilmv.app",
        "https://www.1tamilmv.kiwi",
        "https://tamilmv.ws",
    ]

    @classmethod
    def validate(cls) -> bool:
        """Validate required config."""
        if not cls.TOKEN:
            raise ValueError("TOKEN is required. Get one from @BotFather.")
        if cls.CHANNEL_ID == 0:
            raise ValueError("CHANNEL_ID is required.")
        return True
