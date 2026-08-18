"""Async scraper for 1TamilMV and multi-source torrent engine with proxy rotation,
intelligent keyword/actor enrichment, local catalog caching, and magnet/torrent extraction."""
import asyncio
import logging
import re
from typing import List, Dict, Optional, Set
from urllib.parse import urljoin, quote_plus, unquote

import aiohttp
from bs4 import BeautifulSoup

from bot.config import Config
from bot.catalog import catalog

logger = logging.getLogger(__name__)

# ── Cinematic Short Titles & Star Cast Knowledge Base ─────────────────────────
# Maps short movie titles (< 4 letters or acronyms) to primary star cast, directors, or full titles.
SHORT_TITLES_MAP: Dict[str, List[str]] = {
    # Tamil / Kollywood
    "dna": ["Atharvaa", "Nimisha Sajayan", "Nelson Venkatesan"],
    "leo": ["Badass", "Thalapathy Vijay", "Lokesh Kanagaraj", "Trisha"],
    "don": ["Sivakarthikeyan", "Priyanka Mohan", "Cibi Chakaravarthi"],
    "goat": ["Greatest Of All Time", "Venkat Prabhu", "Vijay"],
    "the goat": ["Greatest Of All Time", "Venkat Prabhu", "Vijay"],
    "96": ["Vijay Sethupathi", "Trisha", "Prem Kumar"],
    "vip": ["Velaiilla Pattadhari", "Dhanush", "Amala Paul"],
    "fir": ["Vishnu Vishal", "Manjima Mohan", "Gautham Menon"],
    "ccv": ["Chekka Chivantha Vaanam", "Mani Ratnam", "Silambarasan", "Arvind Swami"],
    "bro": ["Pawan Kalyan", "Sai Dharam Tej", "Samuthirakani"],
    "sir": ["Dhanush", "Venky Atluri", "Samyuktha"],
    "pt sir": ["Hiphop Tamizha", "Kashmira Pardeshi", "Karthik Venugopalan"],
    "pet": ["Karthik Subbaraj", "Rajinikanth"],
    "petta": ["Rajinikanth", "Karthik Subbaraj", "Simran", "Trisha"],
    "ps1": ["Ponniyin Selvan", "Mani Ratnam", "Vikram", "Aishwarya"],
    "ps2": ["Ponniyin Selvan", "Mani Ratnam", "Vikram", "Trisha"],
    "ps-1": ["Ponniyin Selvan", "Mani Ratnam"],
    "ps-2": ["Ponniyin Selvan", "Mani Ratnam"],
    "i": ["Vikram", "Shankar", "Amy Jackson", "Chiyaan Vikram"],
    "3": ["Dhanush", "Shruti Haasan", "Aishwarya Rajinikanth", "Moonu"],
    "m": ["Suriya", "Madhavan"],
    "ok": ["OK Kanmani", "Dulquer Salmaan", "Nithya Menen", "Mani Ratnam"],
    "sms": ["Siva Manasula Sakthi", "Jiiva", "Anuya Bhagvath", "Rajesh"],
    "arm": ["Tovino Thomas", "Jithin Laal", "Krithi Shetty"],
    "og": ["Pawan Kalyan", "Sujeeth", "Emraan Hashmi"],
    "gvm": ["Gautham Vasudev Menon"],
    "d50": ["Raayan", "Dhanush", "Sundeep Kishan"],
    "t67": ["Leo", "Thalapathy Vijay", "Lokesh Kanagaraj"],
    "t68": ["The Greatest of All Time", "Vijay", "Venkat Prabhu"],
    "t69": ["Jana Nayagan", "Thalapathy Vijay", "H Vinoth"],
    "ak62": ["Vidaa Muyarchi", "Ajith Kumar", "Magizh Thirumeni"],
    "ak63": ["Good Bad Ugly", "Ajith Kumar", "Adhik Ravichandran"],
    "str": ["Silambarasan", "Simbu"],
    "sk": ["Sivakarthikeyan", "Amaran", "Madharaasi"],
    "vjs": ["Vijay Sethupathi", "Maharaja", "Viduthalai"],
    "dq": ["Dulquer Salmaan", "Lucky Baskhar", "King of Kotha"],
    "fahadh": ["Fahadh Faasil", "Aavesham", "Bougainvillea"],
    
    # Telugu / Tollywood
    "rrr": ["SS Rajamouli", "Ram Charan", "Jr NTR"],
    "kgf": ["Yash", "Prashanth Neel", "K.G.F", "Srinidhi Shetty"],
    "kgf 2": ["Yash", "Prashanth Neel", "K.G.F Chapter 2"],
    "kgf 1": ["Yash", "Prashanth Neel", "K.G.F Chapter 1"],
    "ntr": ["Jr NTR", "Devara", "Koratala Siva"],
    "rc15": ["Game Changer", "Ram Charan", "Kiara Advani", "Shankar"],
    "rc16": ["Buchi Babu Sana", "Ram Charan", "Janhvi Kapoor"],
    "svp": ["Sarkaru Vaari Paata", "Mahesh Babu", "Keerthy Suresh"],
    "gkr": ["Guntur Kaaram", "Mahesh Babu", "Sreeleela", "Trivikram"],
    "vvr": ["Vinaya Vidheya Rama", "Ram Charan", "Boyapati Srinu"],
    "mb": ["Mahesh Babu", "SSMB29", "SS Rajamouli"],
    "pk": ["Pawan Kalyan", "Hari Hara Veera Mallu"],

    # Malayalam / Mollywood
    "cbi": ["Mammootty", "K Madhu", "CBI 5 The Brain"],
    "cbi 5": ["Mammootty", "K Madhu", "The Brain"],
    "lucifer": ["Mohanlal", "Prithviraj Sukumaran", "Manju Warrier"],
    "l2": ["Empuraan", "Mohanlal", "Prithviraj Sukumaran"],

    # Hindi / Bollywood
    "jawan": ["Shah Rukh Khan", "Nayanthara", "Atlee"],
    "dunki": ["Shah Rukh Khan", "Taapsee Pannu", "Rajkumar Hirani"],
    "pathaan": ["Shah Rukh Khan", "Deepika Padukone", "Siddharth Anand"],
    "animal": ["Ranbir Kapoor", "Rashmika Mandanna", "Sandeep Reddy Vanga"],
    "kill": ["Lakshya", "Raghav Juyal", "Nikhil Nagesh Bhat"],
    "stree 2": ["Rajkummar Rao", "Shraddha Kapoor", "Amar Kaushik"],
    "fighter": ["Hrithik Roshan", "Deepika Padukone", "Siddharth Anand"],

    # Hollywood / Anime / Classics
    "hp": ["Harry Potter", "Daniel Radcliffe", "Emma Watson"],
    "lotr": ["Lord of the Rings", "Peter Jackson"],
    "sw": ["Star Wars", "George Lucas"],
    "got": ["Game of Thrones", "George R. R. Martin"],
    "hotd": ["House of the Dragon", "Matt Smith"],
    "bb": ["Breaking Bad", "Bryan Cranston"],
    "bcs": ["Better Call Saul", "Bob Odenkirk"],
}

# ── Search API base path (relative to domain) ────────────────────────────────
# 1TamilMV's website uses a custom PHP search API that bypasses the IPS/MySQL
# ft_min_word_len=4 limitation.  This is the exact same endpoint the browser
# calls when you type in the search bar.  It accepts ANY keyword length.
SEARCH_API_PATH = "/search/api/search.php"


class TamilMVScraper:
    """Multi-layer movie scraper with proxy rotation, intelligent short-title expansion,
    local catalog searching, and global multi-source fallback."""

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
        self.catalog = catalog

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

    async def get_latest(self, limit: int = 25) -> List[Dict]:
        """Fetch latest movie topics from 1TamilMV homepage and forum categories."""
        timeout = aiohttp.ClientTimeout(total=10, connect=4)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            domain = self.working_domain
            if not domain:
                domain = await self._find_working_domain(session)
            if not domain:
                # Fallback to local catalog if site is unreachable
                return self.catalog.search("", limit=limit)

            url = domain + "/"
            try:
                async with session.get(url, headers=self.HEADERS, ssl=False) as resp:
                    if resp.status != 200:
                        self.working_domain = None
                        return self.catalog.search("", limit=limit)
                    html = await resp.text()
                    movies = self._parse_movies(html, domain, limit)
                    if movies:
                        self.catalog.insert_movies(movies)
                    return movies
            except Exception as e:
                logger.error(f"Failed to fetch latest movies from {domain}: {e}")
                self.working_domain = None
                return self.catalog.search("", limit=limit)

    def _parse_movies(self, html: str, base_url: str, limit: int) -> List[Dict]:
        """Parse movie entries from HTML."""
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

            is_official = any(k in title.lower() for k in ["proper", "true web-dl", "bluray", "hdrip", "predvd", "official"])
            is_cloud_reupload = any(k in title.lower() for k in ["gdrive", "msd4k", "lrtx", "nowshort"])
            score = (2 if is_official else 1) - (1 if is_cloud_reupload else 0)

            movie_url = urljoin(base_url, href.split("&do=findComment")[0])
            movies.append({
                "title": title,
                "url": movie_url,
                "quality": quality,
                "source": "1TamilMV",
                "score": score,
            })

            if len(movies) >= limit:
                break

        return movies

    async def _expand_query_metadata(self, session: aiohttp.ClientSession, query: str) -> List[str]:
        """Dynamically fetch keyword and actor suggestions using public APIs for unmapped queries."""
        suggestions = []
        clean_q = query.strip()
        
        # 1. DuckDuckGo movie suggestions
        try:
            ddg_url = f"https://duckduckgo.com/ac/?q={quote_plus(clean_q)}%20movie&type=list"
            async with session.get(ddg_url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
                        for s in data[1][:4]:
                            clean_s = re.sub(r"\b(movie|film|tamil|cast|review|rating|release date)\b", "", s, flags=re.I).strip()
                            if len(clean_s) >= 4 and clean_s.lower() != clean_q.lower():
                                suggestions.append(clean_s)
        except Exception:
            pass

        # 2. Wikipedia search API
        try:
            wiki_url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={quote_plus(clean_q)}+film&limit=3&namespace=0&format=json"
            async with session.get(wiki_url, timeout=aiohttp.ClientTimeout(total=2)) as resp:
                if resp.status == 200:
                    wdata = await resp.json(content_type=None)
                    if isinstance(wdata, list) and len(wdata) > 1 and isinstance(wdata[1], list):
                        for item in wdata[1][:3]:
                            c_item = re.sub(r"\s*\([^)]*\)", "", item).strip()
                            if len(c_item) >= 4 and c_item.lower() != clean_q.lower():
                                suggestions.append(c_item)
        except Exception:
            pass

        return list(dict.fromkeys(suggestions))

    async def _search_tamilmv_api(
        self,
        session: aiohttp.ClientSession,
        domain: str,
        query: str,
        page: int = 1,
        per_page: int = 25,
    ) -> List[Dict]:
        """Search 1TamilMV using the official custom JSON search API.
        
        This is the same endpoint the website uses in the browser.
        It has ZERO keyword-length restrictions – even 1-2-3 letter queries
        (DNA, Leo, KGF, 96, VIP, OK, RRR, etc.) return full results.
        
        API endpoint: {domain}/search/api/search.php?q=...&sort=date_desc&page=N&per_page=N
        Returns JSON: {results: [{tid, title, author, date, replies, views, ...}], total, page, per_page, page_count}
        """
        # The API always lives on the canonical .ing domain regardless of which
        # proxy domain the user connected through, but we try the working domain first.
        api_urls = []
        api_urls.append(f"{domain}{SEARCH_API_PATH}")
        # Fallback: canonical domain
        if "1tamilmv.ing" not in domain:
            api_urls.append(f"https://www.1tamilmv.ing{SEARCH_API_PATH}")

        movies = []
        for api_base in api_urls:
            url = f"{api_base}?q={quote_plus(query)}&sort=date_desc&page={page}&per_page={per_page}"
            try:
                timeout = aiohttp.ClientTimeout(total=6)
                async with session.get(url, headers=self.HEADERS, ssl=False, timeout=timeout) as resp:
                    if resp.status != 200:
                        continue
                    data = await resp.json(content_type=None)
                    results = data.get("results", [])
                    if not results:
                        continue

                    for item in results:
                        tid = item.get("tid")
                        title = item.get("title", "")
                        if not tid or not title:
                            continue

                        # Build topic URL from tid
                        slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')[:80]
                        topic_url = f"{domain}/index.php?/forums/topic/{tid}-{slug}/"

                        # Extract quality hints from title
                        quality = "Unknown"
                        for q in ["4K", "2160p", "1080p", "720p", "480p", "HDRip", "WEB-DL", "BluRay", "HQ PreDVD", "PreDVD", "HD"]:
                            if q.lower() in title.lower():
                                quality = q
                                break

                        is_official = any(k in title.lower() for k in ["proper", "true web-dl", "bluray", "hdrip", "predvd", "official"])
                        is_cloud_reupload = any(k in title.lower() for k in ["gdrive", "msd4k", "lrtx", "nowshort"])
                        is_priority = item.get("priority", False)
                        views = item.get("views", 0)

                        score = (3 if is_priority else 2 if is_official else 1)
                        score -= (1 if is_cloud_reupload else 0)
                        # High-view boost
                        if views > 50000:
                            score += 1

                        movies.append({
                            "title": title,
                            "url": topic_url,
                            "quality": quality,
                            "source": "1TamilMV",
                            "score": score,
                        })
                    # Success – don't try fallback domains
                    break
            except Exception as e:
                logger.debug(f"Search API request failed at {api_base} for '{query}': {e}")
                continue

        return movies

    async def _fetch_tamilmv_term(
        self,
        session: aiohttp.ClientSession,
        domain: str,
        term: str,
        filter_query: str,
        is_alias: bool,
        page: int = 1
    ) -> List[Dict]:
        """Legacy fallback: search 1TamilMV using old IPS HTML search.
        Only used when the custom API is unavailable."""
        search_url = f"{domain}/index.php?/search/&q={quote_plus(term)}&search_in=titles&page={page}"
        movies = []
        seen = set()
        
        # Word boundary pattern for accurate matching of short queries
        pattern = r'\b' + re.escape(filter_query.strip()) + r'\b'

        try:
            probe_timeout = aiohttp.ClientTimeout(total=5)
            async with session.get(search_url, headers=self.HEADERS, ssl=False, timeout=probe_timeout) as resp:
                if resp.status != 200:
                    return []
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

                    clean_url = urljoin(domain, href.split("&do=findComment")[0])
                    if clean_url in seen:
                        continue

                    # If this search was triggered via star cast / alias, verify original movie name appears in title
                    if is_alias:
                        if not (re.search(pattern, title, re.IGNORECASE) or filter_query.lower() in title.lower()):
                            continue
                    else:
                        # Direct keyword search: ensure at least one significant query term is present
                        q_words = [w for w in filter_query.lower().split() if len(w) > 2]
                        if q_words and not any(w in title.lower() for w in q_words):
                            continue

                    seen.add(clean_url)

                    quality = "Unknown"
                    for q in ["4K", "2160p", "1080p", "720p", "480p", "HDRip", "WEB-DL", "BluRay", "HQ PreDVD", "PreDVD", "HD"]:
                        if q.lower() in title.lower():
                            quality = q
                            break

                    is_official = any(k in title.lower() for k in ["proper", "true web-dl", "bluray", "hdrip", "predvd", "official"])
                    is_cloud_reupload = any(k in title.lower() for k in ["gdrive", "msd4k", "lrtx", "nowshort"])
                    score = (2 if is_official else 1) - (1 if is_cloud_reupload else 0)

                    movies.append({
                        "title": title,
                        "url": clean_url,
                        "quality": quality,
                        "source": "1TamilMV",
                        "score": score,
                    })
        except Exception as e:
            logger.debug(f"Search request failed for '{term}': {e}")

        return movies

    async def _search_yts_api(self, session: aiohttp.ClientSession, query: str, limit: int = 15) -> List[Dict]:
        """Search YTS/YIFY Movie API for Hollywood, global, and international movies."""
        clean_q = query.strip()
        yts_url = f"https://yts.mx/api/v2/list_movies.json?query_term={quote_plus(clean_q)}&limit={limit}"
        movies = []
        try:
            async with session.get(yts_url, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    items = data.get("data", {}).get("movies", [])
                    for item in items:
                        title_long = item.get("title_long") or f"{item.get('title')} ({item.get('year')})"
                        torrents = item.get("torrents", [])
                        top_quality = torrents[0].get("quality", "1080p") if torrents else "1080p"
                        yts_page = item.get("url") or f"https://yts.mx/movies/{item.get('slug')}"
                        
                        # Store pre-extracted torrent details in special format for fast instant dispatch
                        movies.append({
                            "title": f"{title_long} [YTS HD]",
                            "url": yts_page,
                            "quality": top_quality,
                            "source": "YTS Movie HD",
                            "score": 3,
                            "yts_data": item,
                        })
        except Exception as e:
            logger.debug(f"YTS API search error for '{query}': {e}")
        return movies

    async def search(self, query: str, limit: int = 50) -> List[Dict]:
        """Multi-layer Universal Movie Search Engine:
        1. PRIMARY: 1TamilMV custom JSON search API (zero keyword-length limits).
        2. Local SQLite Catalog instant match.
        3. Smart alias/star-cast fallback via old IPS HTML search (legacy).
        4. Live forum category crawl on-demand.
        5. Global multi-source (YTS / YIFY) torrent fallback for international titles."""
        clean_q = query.strip()
        if not clean_q:
            return []

        clean_lower = clean_q.lower()
        timeout = aiohttp.ClientTimeout(total=14, connect=4)
        
        movies: List[Dict] = []
        seen_urls: Set[str] = set()

        def _dedup_url(url: str) -> str:
            """Normalize topic URL for deduplication by extracting topic ID."""
            m = re.search(r'/topic/(\d+)', url)
            return m.group(1) if m else url

        def _add_movies(items: List[Dict]):
            for m in items:
                url = m.get("url", "")
                key = _dedup_url(url)
                if key and key not in seen_urls:
                    seen_urls.add(key)
                    movies.append(m)

        async with aiohttp.ClientSession(timeout=timeout) as session:
            domain = self.working_domain
            if not domain:
                domain = await self._find_working_domain(session)

            # ── Step 1: PRIMARY – 1TamilMV Custom JSON Search API ────────────────
            # This is the same endpoint the official website uses in the browser.
            # It works for ALL query lengths: DNA, Leo, KGF, 96, VIP, OK, RRR, etc.
            if domain:
                api_results = await self._search_tamilmv_api(
                    session, domain, clean_q, page=1, per_page=min(limit, 50)
                )
                _add_movies(api_results)
                
                # Fetch page 2 if we got a full page of results
                if len(api_results) >= 20:
                    api_page2 = await self._search_tamilmv_api(
                        session, domain, clean_q, page=2, per_page=25
                    )
                    _add_movies(api_page2)

            # ── Step 2: Local SQLite Catalog Instant Search ──────────────────────
            cached_results = self.catalog.search(clean_q, limit=limit)
            if cached_results:
                _add_movies(cached_results)

            # ── Step 3: Alias/Star-cast Legacy IPS Fallback (only if API found few) ──
            if len(movies) < 5:
                terms_to_query: List[tuple[str, bool]] = []

                # Check built-in short titles & acronyms knowledge base
                if clean_lower in SHORT_TITLES_MAP:
                    for alias in SHORT_TITLES_MAP[clean_lower]:
                        terms_to_query.append((alias, True))
                
                # If words >= 4 characters exist, add them as direct queries
                words = [w for w in clean_q.split() if len(w) >= 4]
                if len(clean_q) >= 4:
                    terms_to_query.insert(0, (clean_q, False))
                for w in words:
                    if (w, False) not in terms_to_query and (w, True) not in terms_to_query:
                        terms_to_query.append((w, False))

                # If query has no terms yet, fetch dynamic suggestions
                if not terms_to_query and len(clean_q) < 4:
                    dyn_suggestions = await self._expand_query_metadata(session, clean_q)
                    for s in dyn_suggestions:
                        terms_to_query.append((s, True))

                if domain and terms_to_query:
                    search_tasks = []
                    for term, is_alias in terms_to_query[:4]:
                        search_tasks.append(self._fetch_tamilmv_term(session, domain, term, clean_q, is_alias, page=1))

                    results = await asyncio.gather(*search_tasks, return_exceptions=True)
                    for r in results:
                        if isinstance(r, list):
                            _add_movies(r)

            # ── Step 4: Live Forum Category Scanning (if still few results) ──────
            if domain and len(movies) < 3:
                subforum_urls = [
                    ("Tamil", f"{domain}/index.php?/forums/forum/12-tamil-proper-web-dl-hq-predvd-bluray/"),
                    ("Tamil", f"{domain}/index.php?/forums/forum/11-web-hd-itunes-hd-bluray/"),
                    ("Telugu", f"{domain}/index.php?/forums/forum/24-web-hd-itunes-hd-bluray/"),
                    ("Hindi", f"{domain}/index.php?/forums/forum/58-web-hd-itunes-hd-bluray/"),
                    ("Malayalam", f"{domain}/index.php?/forums/forum/36-web-hd-itunes-hd-bluray/"),
                    ("English", f"{domain}/index.php?/forums/forum/49-web-hd-itunes-hd-bluray/"),
                ]
                crawl_tasks = [
                    self.catalog.crawl_forum_category(session, cat_name, cat_url, self.HEADERS, max_pages=1)
                    for cat_name, cat_url in subforum_urls
                ]
                await asyncio.gather(*crawl_tasks, return_exceptions=True)
                
                fresh_cached = self.catalog.search(clean_q, limit=limit)
                _add_movies(fresh_cached)

            # ── Step 5: Global Multi-Source (YTS API) Fallback ───────────────────
            if len(movies) < 4 or any(w in clean_lower for w in ["hollywood", "english", "bluray", "yts", "yify", "marvel", "dc", "anime"]):
                yts_items = await self._search_yts_api(session, clean_q, limit=10)
                _add_movies(yts_items)

        # Save newly discovered 1TamilMV items into SQLite catalog
        tamilmv_items = [m for m in movies if m.get("source") == "1TamilMV"]
        if tamilmv_items:
            self.catalog.insert_movies(tamilmv_items)

        # Relevancy sorting
        def sort_key(item: Dict) -> int:
            t = item.get("title", "").lower()
            score = item.get("score", 1)
            # Exact word match boost
            pattern = r'\b' + re.escape(clean_lower) + r'\b'
            if re.search(pattern, t):
                score += 5
            elif clean_lower in t:
                score += 2
            if any(q in t for q in ["4k", "2160p", "1080p"]):
                score += 1
            return score

        movies.sort(key=sort_key, reverse=True)
        return movies[:limit]

    async def get_topic_details(self, topic_url: str) -> Dict:
        """Fetch detailed information for a specific topic, including magnet links, direct links, sizes, and poster."""
        # Check if this is a YTS item with pre-extracted data
        if "yts.mx" in topic_url:
            return await self._get_yts_topic_details(topic_url)

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

    async def _get_yts_topic_details(self, yts_url: str) -> Dict:
        """Extract torrent and magnet links from a YTS movie page or API."""
        timeout = aiohttp.ClientTimeout(total=8, connect=4)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            try:
                async with session.get(yts_url) as resp:
                    if resp.status != 200:
                        return {"error": f"HTTP {resp.status}"}
                    html = await resp.text()
                    soup = BeautifulSoup(html, "html.parser")
                    
                    title_tag = soup.find("h1")
                    title = title_tag.get_text(strip=True) if title_tag else "Movie Details"
                    
                    poster = None
                    img_tag = soup.select_one("#movie-poster img, .movie-cover img")
                    if img_tag:
                        poster = img_tag.get("src")
                        
                    releases = []
                    for a in soup.find_all("a", href=True):
                        href = a["href"]
                        if href.startswith("magnet:"):
                            dn_match = re.search(r"dn=([^&]+)", href)
                            dn_name = unquote(dn_match.group(1)) if dn_match else title
                            releases.append({
                                "name": dn_name,
                                "size": "N/A",
                                "torrent_url": "",
                                "magnet": href,
                                "direct_url": "",
                            })
                        elif "yts.mx/torrent/download/" in href or href.endswith(".torrent"):
                            rel_name = a.get_text(strip=True) or f"{title} Torrent"
                            releases.append({
                                "name": f"{title} [{rel_name}]",
                                "size": "N/A",
                                "torrent_url": href,
                                "magnet": "",
                                "direct_url": "",
                            })

                    return {
                        "title": title,
                        "url": yts_url,
                        "poster": poster,
                        "releases": releases,
                        "torrents": releases,
                        "direct_links": [],
                    }
            except Exception as e:
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

            # 2. Fallback to external mirrors if no releases found
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
                size = size_match.group(1) if size_match else "N/A"

                torrents.append({
                    "name": name,
                    "magnet": mag_href,
                    "size": size,
                })

            # 4. Direct links and torrent attachments
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
