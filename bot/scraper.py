"""Async scraper for 1TamilMV with proxy rotation and magnet/torrent extraction."""
import asyncio
import logging
import re
from typing import List, Dict, Optional
from urllib.parse import urljoin, quote_plus, unquote

import aiohttp
from bs4 import BeautifulSoup

from bot.config import Config

logger = logging.getLogger(__name__)

class TamilMVScraper:
    """Scraper for 1TamilMV movie listings and torrent details."""

    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate",
        "DNT": "1",
        "Connection": "keep-alive",
    }

    def __init__(self):
        self.working_domain: Optional[str] = None

    def _get_domains(self) -> List[str]:
        """Get ordered list of candidate domains."""
        target = (Config.TAMILMV_URL or "").strip().rstrip("/")
        all_doms = []
        if target:
            all_doms.append(target)
        for d in Config.PROXY_DOMAINS:
            cleaned = d.strip().rstrip("/")
            if cleaned and cleaned not in all_doms:
                all_doms.append(cleaned)
        return all_doms

    async def _find_working_domain(self, session: aiohttp.ClientSession) -> Optional[str]:
        """Rotate through domains and find one that responds."""
        domains = self._get_domains()
        for domain in domains:
            try:
                probe_timeout = aiohttp.ClientTimeout(total=4, connect=2)
                async with session.get(domain, headers=self.HEADERS, ssl=False, timeout=probe_timeout) as resp:
                    if resp.status == 200:
                        logger.info(f"Working domain found: {domain}")
                        self.working_domain = domain
                        return domain
            except Exception as e:
                logger.debug(f"Domain probe failed {domain}: {e}")
                continue
        logger.error("No working 1TamilMV domain found.")
        return None

    async def get_latest(self, limit: int = 10) -> List[Dict]:
        """Fetch latest movie topics from 1TamilMV homepage."""
        timeout = aiohttp.ClientTimeout(total=10, connect=4)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            domain = self.working_domain
            if not domain:
                domain = await self._find_working_domain(session)
            if not domain:
                return []

            url = domain + "/"
            try:
                async with session.get(url, headers=self.HEADERS, ssl=False) as resp:
                    if resp.status != 200:
                        self.working_domain = None
                        return []
                    html = await resp.text()
                    return self._parse_movies(html, domain, limit)
            except Exception as e:
                logger.error(f"Failed to fetch latest movies from {domain}: {e}")
                self.working_domain = None
                return []

    def _parse_movies(self, html: str, base_url: str, limit: int) -> List[Dict]:
        """Parse movie entries from homepage HTML."""
        soup = BeautifulSoup(html, "html.parser")
        movies = []

        entries = soup.select(".ipsDataItem_main, .structItem-title, article, .xtt-post-title")
        if not entries:
            entries = soup.find_all("a", href=True)

        seen = set()
        for entry in entries[: limit * 6]:
            title_tag = entry if entry.name == "a" else entry.find("a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            href = title_tag.get("href", "")

            if not title or len(title) < 5 or href in seen:
                continue
            if "/topic/" not in href:
                continue
            seen.add(href)

            # Extract quality hints from title
            quality = "Unknown"
            for q in ["4K", "2160p", "1080p", "720p", "480p", "HDRip", "WEB-DL", "BluRay", "HQ PreDVD", "PreDVD", "HD"]:
                if q.lower() in title.lower():
                    quality = q
                    break

            movie_url = urljoin(base_url, href)
            movies.append({
                "title": title,
                "url": movie_url,
                "quality": quality,
                "source": "1TamilMV",
            })

            if len(movies) >= limit:
                break

        logger.info(f"Parsed {len(movies)} movies from {base_url}")
        return movies

    async def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search 1TamilMV using the search endpoint with intelligent keyword fallback."""
        timeout = aiohttp.ClientTimeout(total=10, connect=4)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            domain = self.working_domain
            if not domain:
                domain = await self._find_working_domain(session)
            if not domain:
                return []

            words = [w.strip() for w in query.split() if len(w.strip()) > 1]
            search_terms = [query] + words if len(words) > 1 else [query]

            movies = []
            seen = set()

            for term in search_terms:
                search_url = f"{domain}/index.php?/search/&q={quote_plus(term)}&search_in=titles"
                try:
                    probe_timeout = aiohttp.ClientTimeout(total=6)
                    async with session.get(search_url, headers=self.HEADERS, ssl=False, timeout=probe_timeout) as resp:
                        if resp.status != 200:
                            continue
                        html = await resp.text()
                        soup = BeautifulSoup(html, "html.parser")

                        for a in soup.find_all("a", href=True):
                            href = a["href"]
                            if "/topic/" not in href:
                                continue
                            title = a.get_text(strip=True)
                            if not title or len(title) < 5:
                                continue
                            if title.lower() in ["languages", "reply", "replies", "next", "previous"]:
                                continue
                            if re.match(r"^\d+\s+repl(y|ies)$", title, re.I):
                                continue

                            clean_url = href.split("&do=findComment")[0]
                            if clean_url in seen:
                                continue

                            # Verify that key terms match
                            if not all(w.lower() in title.lower() for w in words):
                                continue

                            seen.add(clean_url)

                            quality = "Unknown"
                            for q in ["4K", "2160p", "1080p", "720p", "480p", "HDRip", "WEB-DL", "BluRay", "HQ PreDVD", "PreDVD", "HD"]:
                                if q.lower() in title.lower():
                                    quality = q
                                    break

                            movies.append({
                                "title": title,
                                "url": urljoin(domain, clean_url),
                                "quality": quality,
                                "source": "1TamilMV",
                            })
                            if len(movies) >= limit:
                                break
                except Exception as e:
                    logger.debug(f"Search request failed for {term}: {e}")

                if movies:
                    break

            # Fallback to recent items if search engine returned nothing
            if not movies:
                latest_movies = await self.get_latest(limit=30)
                q_lower = query.lower()
                movies = [m for m in latest_movies if q_lower in m["title"].lower()]

            return movies[:limit]

    async def get_topic_details(self, topic_url: str) -> Dict:
        """Fetch detailed information for a specific topic, including magnet links, direct links, sizes, and poster."""
        timeout = aiohttp.ClientTimeout(total=12, connect=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(topic_url, headers=self.HEADERS, ssl=False) as resp:
                    if resp.status != 200:
                        return {"error": f"HTTP {resp.status}"}
                    html = await resp.text()
                    return self._parse_topic_html(html, topic_url)
            except Exception as e:
                logger.error(f"Failed to fetch topic details for {topic_url}: {e}")
                return {"error": str(e)}

    def _parse_topic_html(self, html: str, topic_url: str) -> Dict:
        """Parse topic details, magnets, direct links, and poster from topic page HTML."""
        soup = BeautifulSoup(html, "html.parser")

        title_tag = soup.find("h1", {"class": "ipsType_pageTitle"}) or soup.find("h1")
        title = title_tag.get_text(strip=True) if title_tag else "Movie Details"

        poster = None
        comment = soup.find("div", {"data-role": "commentContent"}) or soup.find("article")
        if comment:
            for img in comment.find_all("img"):
                src = img.get("src") or img.get("data-src") or ""
                if any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
                    if not any(bad in src.lower() for bad in ["emoticons", "theme", "border", "utorrent", "logo.png"]):
                        poster = src
                        break

        torrents = []
        direct_links = []

        if comment:
            # 1. Magnets
            magnet_tags = comment.find_all("a", href=lambda h: h and h.startswith("magnet:"))
            for m in magnet_tags:
                mag_href = m["href"]
                name_match = re.search(r"dn=([^&]+)", mag_href)
                name = unquote(name_match.group(1)) if name_match else title

                name = re.sub(r"^www\.[^ -]+ - ", "", name, flags=re.I)
                size_match = re.search(r"(\d+(?:\.\d+)?\s*(?:GB|MB))", name, re.I)
                size = size_match.group(1) if size_match else "N/A"

                torrents.append({
                    "name": name,
                    "magnet": mag_href,
                    "size": size,
                })

            # 2. Torrent attachments & direct download hosts
            for a in comment.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                if any(host in href.lower() for host in ["shrinkme", "cyberloom", "gofile", "mega.nz", "pixeldrain", "streamtape", "attachment.php"]):
                    if not any(d["url"] == href for d in direct_links):
                        direct_links.append({
                            "name": text if len(text) > 3 and not text.startswith("http") else "Download Mirror",
                            "url": href
                        })

        return {
            "title": title,
            "url": topic_url,
            "poster": poster,
            "torrents": torrents,
            "direct_links": direct_links,
        }

    async def close(self):
        pass
