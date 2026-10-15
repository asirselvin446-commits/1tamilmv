"""Configuration loader for 1TamilVT-TG."""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Bot configuration."""
    TOKEN: str = os.getenv("TOKEN", "")
    CHANNEL_ID: int = int(os.getenv("CHANNEL_ID", "0"))
    CHANNEL_USERNAME: str = os.getenv("CHANNEL_USERNAME", "").lstrip("@")
    # Access control: Set ADMIN_ID or ALLOWED_USERS to restrict access to yourself only
    ADMIN_ID: int = int(os.getenv("ADMIN_ID", "0"))
    ALLOWED_USERS: list = [
        int(x.strip()) for x in os.getenv("ALLOWED_USERS", "").split(",") if x.strip().lstrip("-").isdigit()
    ]
    CHANNEL_INVITE_LINK: str = os.getenv("CHANNEL_INVITE_LINK", "")

    TAMILMV_URL: str = os.getenv("TAMILMV_URL", "https://www.1tamilmv.ing")
    WEBHOOK_URL: str = os.getenv("WEBHOOK_URL", "")
    PORT: int = int(os.getenv("PORT", "8080"))
    SCRAPE_INTERVAL: int = int(os.getenv("SCRAPE_INTERVAL", "300"))
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Fallback proxy list for 1TamilMV domains
    PROXY_DOMAINS: list = [
        "https://www-1tamilmv-solar.translate.goog",
        "https://www.1tamilmv.capital",
        "https://www.1tamilmv.li",
        "https://www.1tamilmv.solar",
        "https://www.1tamilmv.ing",
        "https://www.1tamilmv.pm",
        "https://www.1tamilmv.vin",
        "https://www.1tamilmv.wf",
        "https://www.1tamilmv.yt",
        "https://www.1tamilmv.cx",
        "https://www.1tamilmv.ws",
        "https://www.1tamilmv.fi",
        "https://www.1tamilmv.dad",
        "https://www.1tamilmv.in",
        "https://www.1tamilmv.app",
        "https://www.1tamilmv.kiwi",
    ]

    @classmethod
    def get_authorized_users(cls) -> set:
        """Return set of authorized user IDs."""
        users = set(cls.ALLOWED_USERS)
        if cls.ADMIN_ID:
            users.add(cls.ADMIN_ID)
        return users

    @classmethod
    def validate(cls) -> bool:
        """Validate required config."""
        if not cls.TOKEN:
            raise ValueError("TOKEN is required. Get one from @BotFather.")
        return True
