import json
import logging
import os
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from typing import List, Dict, Tuple
from app.config import WEB_SEARCH_ALLOW_COMMUNITY, WEB_SEARCH_RANKING, LOCAL_EMBEDDING_MODEL


LEARN_SEARCH_ENDPOINT = "https://learn.microsoft.com/api/search"
LEARN_ANSWERS_SEARCH_URL = "https://learn.microsoft.com/en-us/answers/search.html"
SUPPORT_SEARCH_URL = "https://support.microsoft.com/en-us/search/results"
TECHCOMMUNITY_SEARCH_URL = "https://techcommunity.microsoft.com/t5/forums/searchpage/tab/message"
STACKOVERFLOW_SEARCH_URL = "https://stackoverflow.com/search"
REDDIT_AZURE_SUPPORT_SEARCH_URL = "https://www.reddit.com/r/MSFTAzureSupport/search/"
ALLOWED_DOMAINS = [
    "learn.microsoft.com",
    "support.microsoft.com",
    "techcommunity.microsoft.com",
    "stackoverflow.com",
    "reddit.com",
]

MICROSOFT_ONLY_DOMAINS = [
    "learn.microsoft.com",
    "support.microsoft.com",
    "techcommunity.microsoft.com",
]

logger = logging.getLogger(__name__)

_semantic_model = None


def _get_semantic_model():
    global _semantic_model
    if _semantic_model is None:
        from sentence_transformers import SentenceTransformer

        model_name = LOCAL_EMBEDDING_MODEL
        _semantic_model = SentenceTransformer(model_name, device="cpu")
    return _semantic_model


def _ranking_mode() -> str:
    return WEB_SEARCH_RANKING.strip().lower()


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    return float(dot)


def _semantic_rank_results(
    query: str, results: List[Dict[str, str]], top_k: int
) -> List[Dict[str, str]]:
    if not results:
        return results
    model = _get_semantic_model()
    query_vec = model.encode([query], normalize_embeddings=True)[0].tolist()
    scored: List[Tuple[Dict[str, str], float]] = []
    for item in results:
        text = " ".join([item.get("title", ""), item.get("snippet", "")]).strip()
        if not text:
            continue
        vec = model.encode([text], normalize_embeddings=True)[0].tolist()
        scored.append((item, _cosine_similarity(query_vec, vec)))
    if not scored:
        return results
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [item for item, _score in scored[:top_k]]


class _ListTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capture = []
        self._in_li = False
        self._li_texts: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "li":
            self._in_li = True
            self._capture = []

    def handle_endtag(self, tag):
        if tag == "li" and self._in_li:
            text = " ".join(self._capture).strip()
            if text:
                self._li_texts.append(text)
            self._in_li = False
            self._capture = []

    def handle_data(self, data):
        if self._in_li:
            self._capture.append(data)

    @property
    def list_items(self) -> List[str]:
        return self._li_texts


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._links: List[Tuple[str, str]] = []
        self._current_href: str | None = None
        self._capture: List[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            for key, value in attrs:
                if key == "href" and value:
                    self._current_href = value
                    self._capture = []

    def handle_endtag(self, tag):
        if tag == "a" and self._current_href:
            text = " ".join(self._capture).strip()
            self._links.append((self._current_href, text))
            self._current_href = None
            self._capture = []

    def handle_data(self, data):
        if self._current_href is not None:
            self._capture.append(data)

    @property
    def links(self) -> List[Tuple[str, str]]:
        return self._links


def _fetch_url(url: str, headers: Dict[str, str] | None = None) -> str:
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=12) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def search_learn_api(query: str, count: int = 3, use_filter: bool = True) -> List[Dict[str, str]]:
    params = {
        "search": query,
        "$top": str(count),
    }
    if use_filter:
        params["$filter"] = "scope eq 'Learn'"
    url = LEARN_SEARCH_ENDPOINT + "?" + urllib.parse.urlencode(params)
    raw = _fetch_url(url)
    data = json.loads(raw)
    results: List[Dict[str, str]] = []
    for item in data.get("results", []):
        title = item.get("title")
        link = item.get("url")
        if not title or not link:
            continue
        results.append({"title": title, "url": link, "snippet": item.get("summary") or ""})
        if len(results) >= count:
            break
    return results


def search_html_page(url: str, count: int = 3) -> List[Dict[str, str]]:
    html = _fetch_url(url, headers={"User-Agent": "Mozilla/5.0 (SupportAI)"})
    parser = _AnchorParser()
    parser.feed(html)
    results: List[Dict[str, str]] = []
    seen: set[str] = set()
    for href, text in parser.links:
        if href.startswith("/"):
            href = urllib.parse.urljoin(url, href)
        if not href.startswith("http"):
            continue
        if not any(domain in href for domain in ALLOWED_DOMAINS):
            continue
        if href in seen:
            continue
        seen.add(href)
        title = text or "Support guidance"
        results.append({"title": title, "url": href, "snippet": ""})
        if len(results) >= count:
            break
    return results


def extract_list_items(html: str, max_items: int = 20) -> List[str]:
    parser = _ListTextParser()
    parser.feed(html)
    items = [item.strip() for item in parser.list_items if item.strip()]
    return items[:max_items]


def fetch_page_text(url: str) -> Tuple[str, List[str]]:
    headers = {"User-Agent": "Mozilla/5.0 (SupportAI)"}
    html = _fetch_url(url, headers=headers)
    list_items = extract_list_items(html)

    # crude text extraction: remove tags by splitting on '<'
    chunks = []
    for part in html.split("<"):
        text = part.split(">", 1)[-1]
        cleaned = " ".join(text.split())
        if cleaned:
            chunks.append(cleaned)
    text = " ".join(chunks)
    return text, list_items


def build_query(title: str, description: str) -> str:
    combined = f"{title} {description}".strip()
    if len(combined) > 200:
        combined = combined[:200]
    return combined


def _allow_community() -> bool:
    return WEB_SEARCH_ALLOW_COMMUNITY.strip().lower() in {"1", "true", "yes"}


def _extract_keywords(query: str) -> List[str]:
    stop = {
        "the",
        "and",
        "for",
        "with",
        "from",
        "that",
        "this",
        "into",
        "your",
        "about",
        "when",
        "what",
        "where",
        "which",
        "would",
        "could",
        "should",
        "azure",
        "microsoft",
    }
    raw = [w.strip().lower() for w in query.replace("/", " ").split()]
    words = [w for w in raw if len(w) >= 3 and w.isalnum() and w not in stop]
    return list(dict.fromkeys(words))


def _score_result(item: Dict[str, str], keywords: List[str]) -> int:
    hay = " ".join([item.get("title", ""), item.get("url", ""), item.get("snippet", "")]).lower()
    return sum(1 for k in keywords if k in hay)


def _filter_results(results: List[Dict[str, str]], query: str) -> List[Dict[str, str]]:
    keywords = _extract_keywords(query)
    if not keywords:
        return results
    scored = [(item, _score_result(item, keywords)) for item in results]
    filtered = [item for item, score in scored if score >= 2]
    return filtered


def search_microsoft_sites(query: str, count: int = 3) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []

    try:
        results.extend(search_learn_api(query, count=count, use_filter=True))
        if not results:
            results.extend(search_learn_api(query, count=count, use_filter=False))
    except Exception:
        pass

    logger.info("Web search: learn results=%d", len(results))

    if len(results) < count:
        answers_url = LEARN_ANSWERS_SEARCH_URL + "?" + urllib.parse.urlencode({"query": query})
        try:
            results.extend(search_html_page(answers_url, count=count - len(results)))
        except Exception:
            pass

    logger.info("Web search: answers results=%d", len(results))

    if len(results) < count:
        support_url = SUPPORT_SEARCH_URL + "?" + urllib.parse.urlencode({"query": query})
        try:
            results.extend(search_html_page(support_url, count=count - len(results)))
        except Exception:
            pass

    logger.info("Web search: support results=%d", len(results))

    if len(results) < count:
        tech_url = TECHCOMMUNITY_SEARCH_URL + "?" + urllib.parse.urlencode({"query": query})
        try:
            results.extend(search_html_page(tech_url, count=count - len(results)))
        except Exception:
            pass

    logger.info("Web search: techcommunity results=%d", len(results))

    if _allow_community() and len(results) < count:
        stack_url = STACKOVERFLOW_SEARCH_URL + "?" + urllib.parse.urlencode({"q": query})
        try:
            results.extend(search_html_page(stack_url, count=count - len(results)))
        except Exception:
            pass

        logger.info("Web search: stackoverflow results=%d", len(results))

    if _allow_community() and len(results) < count:
        reddit_url = REDDIT_AZURE_SUPPORT_SEARCH_URL + "?" + urllib.parse.urlencode(
            {"q": query, "restrict_sr": "1"}
        )
        try:
            results.extend(search_html_page(reddit_url, count=count - len(results)))
        except Exception:
            pass

        logger.info("Web search: reddit results=%d", len(results))

    if _ranking_mode() == "semantic":
        try:
            ranked = _semantic_rank_results(query, results, count)
            logger.info("Web search: semantic results=%d", len(ranked))
            return ranked[:count]
        except Exception:
            logger.info("Web search: semantic ranking failed (using unfiltered)")
            return results[:count]

    logger.info("Web search: semantic ranking disabled")
    return results[:count]