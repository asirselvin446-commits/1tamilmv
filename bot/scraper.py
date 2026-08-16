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
                probe_timeout = aiohttp.ClientTimeout(total=3, connect=2)
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

    async def search(self, query: str, limit: int = 40) -> List[Dict]:
        """Search 1TamilMV using the search endpoint with intelligent keyword fallback and ranking."""
        timeout = aiohttp.ClientTimeout(total=12, connect=4)
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
                # Fetch up to 4 pages of search results to find all available releases
                for page in range(1, 5):
                    search_url = f"{domain}/index.php?/search/&q={quote_plus(term)}&search_in=titles&page={page}"
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

                                # Calculate relevancy score (official/direct torrent titles scored higher)
                                is_official = any(k in title.lower() for k in ["proper", "true web-dl", "bluray", "hdrip", "predvd", "official"])
                                is_cloud_reupload = any(k in title.lower() for k in ["gdrive", "msd4k", "lrtx", "nowshort"])

                                movies.append({
                                    "title": title,
                                    "url": urljoin(domain, clean_url),
                                    "quality": quality,
                                    "source": "1TamilMV",
                                    "score": (2 if is_official else 1) - (1 if is_cloud_reupload else 0),
                                })
                    except Exception as e:
                        logger.debug(f"Search request failed for {term} page {page}: {e}")

                if movies:
                    break

            # Fallback to recent items if search engine returned nothing
            if not movies:
                latest_movies = await self.get_latest(limit=30)
                q_lower = query.lower()
                movies = [m for m in latest_movies if q_lower in m["title"].lower()]

            # Sort by relevancy score (official torrents first)
            movies.sort(key=lambda x: x.get("score", 0), reverse=True)
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
        releases = []

        AD_DOMAINS = [
            "gplinks", "nowshort", "shrinkme", "droplink", "shorturl",
            "adbull", "linkvertise", "ouo.io", "adfocus", "tinyurl", "bitly"
        ]

        if comment:
            all_links = comment.find_all("a", href=True)

            # 1. Structured release extraction
            i = 0
            while i < len(all_links):
                a = all_links[i]
                href = a["href"]
                text = a.get_text(strip=True)

                if "attachment.php" in href or href.lower().endswith(".torrent"):
                    raw_name = text or ""
                    clean_name = re.sub(r"^www\.[^ -]+ - ", "", raw_name, flags=re.I)
                    clean_name = re.sub(r"\.torrent$", "", clean_name, flags=re.I)

                    size_match = re.search(r"(\d+(?:\.\d+)?\s*(?:GB|MB))", clean_name, re.I)
                    size = size_match.group(1) if size_match else "N/A"

                    magnet_url = ""
                    direct_url = ""

                    # Scan siblings ahead for magnet & direct cloud links
                    for j in range(i + 1, min(i + 4, len(all_links))):
                        next_href = all_links[j]["href"]
                        if next_href.startswith("magnet:"):
                            magnet_url = next_href
                            if size == "N/A":
                                xl_match = re.search(r"xl=(\d+)", next_href)
                                if xl_match:
                                    bytes_val = int(xl_match.group(1))
                                    if bytes_val >= 1024**3:
                                        size = f"{bytes_val / (1024**3):.2f} GB"
                                    elif bytes_val >= 1024**2:
                                        size = f"{bytes_val / (1024**2):.1f} MB"
                        elif any(host in next_href.lower() for host in ["cyberloom", "gofile", "mega.nz", "pixeldrain", "1fichier", "mediafire", "streamtape"]):
                            if not any(bad in next_href.lower() for bad in AD_DOMAINS):
                                direct_url = next_href

                    releases.append({
                        "name": clean_name if len(clean_name) > 5 else title,
                        "size": size,
                        "torrent_url": urljoin(topic_url, href),
                        "magnet": magnet_url,
                        "direct_url": direct_url,
                    })
                elif href.startswith("magnet:") and not any(r.get("magnet") == href for r in releases):
                    mag_href = href
                    name_match = re.search(r"dn=([^&]+)", mag_href)
                    name = unquote(name_match.group(1)) if name_match else title
                    name = re.sub(r"^www\.[^ -]+ - ", "", name, flags=re.I)
                    size_match = re.search(r"(\d+(?:\.\d+)?\s*(?:GB|MB))", name, re.I)
                    if size_match:
                        size = size_match.group(1)
                    else:
                        xl_match = re.search(r"xl=(\d+)", mag_href)
                        if xl_match:
                            bytes_val = int(xl_match.group(1))
                            if bytes_val >= 1024**3:
                                size = f"{bytes_val / (1024**3):.2f} GB"
                            elif bytes_val >= 1024**2:
                                size = f"{bytes_val / (1024**2):.1f} MB"
                            else:
                                size = "N/A"
                        else:
                            size = "N/A"

                    releases.append({
                        "name": name,
                        "size": size,
                        "torrent_url": "",
                        "magnet": mag_href,
                        "direct_url": "",
                    })
                i += 1

            # 2. If NO torrent/magnet releases found, extract alternate / external download links (fallback)
            if not releases:
                alt_idx = 1
                for a in all_links:
                    href = a["href"]
                    text = a.get_text(strip=True)
                    if any(bad in href.lower() for bad in ["t.me/", "/topic/", "/forum/", "/profile/", "/login", ".jpg", ".png", ".gif", ".webp", "javascript:"]):
                        continue
                    if href.startswith("http://") or href.startswith("https://"):
                        if not any(r.get("direct_url") == href for r in releases):
                            label = text if text and len(text) > 3 and not text.startswith("http") else f"Alternate Link #{alt_idx}"
                            releases.append({
                                "name": f"Alternate Link #{alt_idx} ({label})" if label != f"Alternate Link #{alt_idx}" else f"Alternate Link #{alt_idx}",
                                "size": "N/A",
                                "torrent_url": "",
                                "magnet": "",
                                "direct_url": href,
                            })
                            direct_links.append({
                                "name": f"⚡ {label}",
                                "url": href
                            })
                            alt_idx += 1

            # 3. Magnets list
            magnet_tags = comment.find_all("a", href=lambda h: h and h.startswith("magnet:"))
            for m in magnet_tags:
                mag_href = m["href"]
                name_match = re.search(r"dn=([^&]+)", mag_href)
                name = unquote(name_match.group(1)) if name_match else title

                name = re.sub(r"^www\.[^ -]+ - ", "", name, flags=re.I)
                size_match = re.search(r"(\d+(?:\.\d+)?\s*(?:GB|MB))", name, re.I)
                if size_match:
                    size = size_match.group(1)
                else:
                    xl_match = re.search(r"xl=(\d+)", mag_href)
                    if xl_match:
                        bytes_val = int(xl_match.group(1))
                        if bytes_val >= 1024 * 1024 * 1024:
                            size = f"{bytes_val / (1024**3):.2f} GB"
                        elif bytes_val >= 1024 * 1024:
                            size = f"{bytes_val / (1024**2):.1f} MB"
                        else:
                            size = "N/A"
                    else:
                        size = "N/A"

                torrents.append({
                    "name": name,
                    "magnet": mag_href,
                    "size": size,
                })

            # 4. Direct links and torrent attachments (excluding ad shorteners)
            for a in comment.find_all("a", href=True):
                href = a["href"]
                text = a.get_text(strip=True)
                if any(bad in href.lower() for bad in AD_DOMAINS):
                    continue
                if any(host in href.lower() for host in ["cyberloom", "gofile", "mega.nz", "pixeldrain", "attachment.php"]):
                    if not any(d["url"] == href for d in direct_links):
                        clean_name = re.sub(r"^www\.[^ -]+ - ", "", text, flags=re.I)
                        if "attachment.php" in href.lower() or href.lower().endswith(".torrent") or text.lower().endswith(".torrent"):
                            display_name = f"📄 {clean_name}" if len(clean_name) > 5 else "📄 Torrent File"
                        elif "cyberloom" in href.lower():
                            display_name = "⚡ CyberLoom Fast Direct Link"
                        elif "gofile" in href.lower():
                            display_name = "⚡ GoFile Direct Download"
                        elif "pixeldrain" in href.lower():
                            display_name = "⚡ PixelDrain Direct Download"
                        elif "mega.nz" in href.lower():
                            display_name = "⚡ Mega.nz Mirror"
                        else:
                            display_name = clean_name if len(clean_name) > 3 and not clean_name.startswith("http") else "Download Mirror"

                        direct_links.append({
                            "name": display_name,
                            "url": href
                        })

        return {
            "title": title,
            "url": topic_url,
            "poster": poster,
            "releases": releases,
            "torrents": torrents,
            "direct_links": direct_links,
        }

    async def close(self):
        pass
