"""Local SQLite catalog and fast forum cache for 1TamilMV releases."""
import asyncio
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Generator, List, Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
DB_PATH = os.path.join(DB_DIR, "catalog.db")

class MovieCatalog:
    """Manages the local SQLite database for instantaneous movie searches without length restrictions."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize SQLite tables and indexes."""
        with self._get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS movies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    url TEXT UNIQUE NOT NULL,
                    quality TEXT DEFAULT 'Unknown',
                    language TEXT DEFAULT 'Tamil',
                    source TEXT DEFAULT '1TamilMV',
                    score INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_movies_title ON movies(title)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_movies_created ON movies(created_at DESC)")
            conn.commit()

    def insert_movies(self, movies: List[Dict]) -> int:
        """Insert or ignore a batch of scraped movies into the database."""
        if not movies:
            return 0
        inserted = 0
        with self._get_connection() as conn:
            cur = conn.cursor()
            for m in movies:
                title = (m.get("title") or "").strip()
                url = (m.get("url") or "").strip()
                if not title or not url or len(title) < 4:
                    continue
                quality = m.get("quality", "Unknown")
                language = m.get("language", "Tamil")
                source = m.get("source", "1TamilMV")
                score = m.get("score", 1)

                try:
                    cur.execute("""
                        INSERT INTO movies (title, url, quality, language, source, score, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(url) DO UPDATE SET
                            title=excluded.title,
                            quality=excluded.quality,
                            score=excluded.score
                    """, (title, url, quality, language, source, score))
                    inserted += 1
                except Exception as e:
                    logger.debug(f"Error inserting movie {title}: {e}")
            conn.commit()
        return inserted

    def search(self, query: str, limit: int = 40) -> List[Dict]:
        """Fast substring and keyword search on local catalog with zero word-length limitations."""
        clean_q = query.strip()
        if not clean_q:
            return []

        words = [w.strip() for w in clean_q.split() if w.strip()]
        results = []

        with self._get_connection() as conn:
            cur = conn.cursor()

            # 1. Exact substring match
            pattern = f"%{clean_q}%"
            cur.execute("""
                SELECT title, url, quality, language, source, score
                FROM movies
                WHERE title LIKE ?
                ORDER BY score DESC, id DESC
                LIMIT ?
            """, (pattern, limit))
            rows = cur.fetchall()

            for row in rows:
                results.append(dict(row))

            # 2. Multi-word AND matching if multi-word query
            if len(words) > 1 and len(results) < limit:
                where_clauses = " AND ".join(["title LIKE ?" for _ in words])
                params = [f"%{w}%" for w in words] + [limit - len(results)]
                cur.execute(f"""
                    SELECT title, url, quality, language, source, score
                    FROM movies
                    WHERE {where_clauses}
                    ORDER BY score DESC, id DESC
                    LIMIT ?
                """, params)
                for row in cur.fetchall():
                    item = dict(row)
                    if not any(r["url"] == item["url"] for r in results):
                        results.append(item)

        return results[:limit]

    def get_total_count(self) -> int:
        """Get total number of cached movies."""
        try:
            with self._get_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT COUNT(*) FROM movies")
                row = cur.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0

    async def crawl_forum_category(
        self,
        session: aiohttp.ClientSession,
        category_name: str,
        category_url: str,
        headers: Dict,
        max_pages: int = 3
    ) -> List[Dict]:
        """Crawl pages of a specific forum category and index releases."""
        scraped = []
        for page in range(1, max_pages + 1):
            url = f"{category_url}page/{page}/" if page > 1 else category_url
            try:
                probe_timeout = aiohttp.ClientTimeout(total=6)
                async with session.get(url, headers=headers, ssl=False, timeout=probe_timeout) as resp:
                    if resp.status != 200:
                        continue
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if "/topic/" not in href:
                            continue
                        title = a.get_text(strip=True)
                        if not title or len(title) < 5 or any(bad in title.lower() for bad in ["reply", "replies", "next", "previous", "languages"]):
                            continue
                        if re.match(r"^\d+\s+repl(y|ies)$", title, re.I):
                            continue

                        clean_url = href.split("&do=findComment")[0]
                        quality = "Unknown"
                        for q in ["4K", "2160p", "1080p", "720p", "480p", "HDRip", "WEB-DL", "BluRay", "HQ PreDVD", "PreDVD", "HD"]:
                            if q.lower() in title.lower():
                                quality = q
                                break

                        is_official = any(k in title.lower() for k in ["proper", "true web-dl", "bluray", "hdrip", "predvd", "official"])
                        is_cloud_reupload = any(k in title.lower() for k in ["gdrive", "msd4k", "lrtx", "nowshort"])
                        score = (2 if is_official else 1) - (1 if is_cloud_reupload else 0)

                        scraped.append({
                            "title": title,
                            "url": clean_url,
                            "quality": quality,
                            "language": category_name,
                            "source": "1TamilMV",
                            "score": score,
                        })
            except Exception as e:
                logger.debug(f"Error crawling {url}: {e}")

        if scraped:
            self.insert_movies(scraped)
        return scraped

    async def sync_all_forums(self, session: aiohttp.ClientSession, domain: str, headers: Dict, max_pages: int = 2) -> int:
        """Background synchronization of key forum categories across all languages."""
        if not domain:
            return 0

        categories = [
            ("Tamil", f"{domain}/index.php?/forums/forum/12-tamil-proper-web-dl-hq-predvd-bluray/"),
            ("Tamil", f"{domain}/index.php?/forums/forum/11-web-hd-itunes-hd-bluray/"),
            ("Tamil", f"{domain}/index.php?/forums/forum/10-predvd-dvdscr-cam-tc/"),
            ("Tamil", f"{domain}/index.php?/forums/forum/18-tamil-dubbed-movies/"),
            ("Tamil", f"{domain}/index.php?/forums/forum/9-tamil-language/"),
            ("Telugu", f"{domain}/index.php?/forums/forum/22-telugu-language/"),
            ("Telugu", f"{domain}/index.php?/forums/forum/24-web-hd-itunes-hd-bluray/"),
            ("Malayalam", f"{domain}/index.php?/forums/forum/34-malayalam-language/"),
            ("Malayalam", f"{domain}/index.php?/forums/forum/36-web-hd-itunes-hd-bluray/"),
            ("Hindi", f"{domain}/index.php?/forums/forum/56-hindi-language/"),
            ("Hindi", f"{domain}/index.php?/forums/forum/58-web-hd-itunes-hd-bluray/"),
            ("Kannada", f"{domain}/index.php?/forums/forum/67-kannada-language/"),
            ("English", f"{domain}/index.php?/forums/forum/45-english-language/"),
            ("English", f"{domain}/index.php?/forums/forum/49-web-hd-itunes-hd-bluray/"),
        ]

        tasks = [
            self.crawl_forum_category(session, cat_name, cat_url, headers, max_pages=max_pages)
            for cat_name, cat_url in categories
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        total_scraped = sum(len(r) for r in results if isinstance(r, list))
        logger.info(f"Forum catalog sync completed: {total_scraped} topics parsed.")
        return total_scraped

# Global catalog singleton
catalog = MovieCatalog()
