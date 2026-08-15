"""Entry point for running the bot via `python -m bot`."""
import asyncio
import logging
from bot.main import main, scraper

logger = logging.getLogger(__name__)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
    finally:
        try:
            asyncio.run(scraper.close())
        except Exception:
            pass
