"""
Web Search Utilities
Provides web search capabilities using Bing Search API or alternative methods.
"""

import json
import logging
import urllib.parse
import urllib.request
from typing import List, Dict
from html.parser import HTMLParser

from app.config import (
    BING_SEARCH_API_KEY,
    BING_SEARCH_ENDPOINT,
    WEB_SEARCH_TIMEOUT,
)


logger = logging.getLogger(__name__)


class _ContentExtractor(HTMLParser):
    """Extracts readable text content from HTML."""
    
    def __init__(self):
        super().__init__()
        self.text_chunks = []
        self._skip_tags = {'script', 'style', 'nav', 'header', 'footer'}
        self._current_tag = None
    
    def handle_starttag(self, tag, attrs):
        self._current_tag = tag
    
    def handle_endtag(self, tag):
        self._current_tag = None
    
    def handle_data(self, data):
        if self._current_tag not in self._skip_tags:
            text = data.strip()
            if text and len(text) > 15:  # Ignore very short fragments
                self.text_chunks.append(text)
    
    def get_text(self, max_length: int = 3000) -> str:
        """Get extracted text up to max_length characters."""
        full_text = " ".join(self.text_chunks)
        return full_text[:max_length] if len(full_text) > max_length else full_text


def search_web(query: str, count: int = 10) -> List[Dict[str, str]]:
    """
    Search the web using Bing Search API or fallback methods.
    
    Args:
        query: Search query string
        count: Number of results to return
        
    Returns:
        List of dictionaries with keys: title, url, snippet
    """
    logger.info(f"Web search query: '{query}' (requesting {count} results)")
    
    # Try Bing Search API first
    if BING_SEARCH_API_KEY:
        try:
            results = _bing_search(query, count)
            logger.info(f"Bing Search returned {len(results)} results")
            return results
        except Exception as e:
            logger.warning(f"Bing Search API failed: {e}, falling back to DuckDuckGo")
    
    # Fallback to DuckDuckGo
    try:
        results = _duckduckgo_search(query, count)
        logger.info(f"DuckDuckGo search returned {len(results)} results")
        return results
    except Exception as e:
        logger.error(f"All web search methods failed: {e}")
        return []


def _bing_search(query: str, count: int) -> List[Dict[str, str]]:
    """Search using Bing Web Search API."""
    
    params = {
        "q": query,
        "count": str(count),
        "responseFilter": "Webpages",
        "textDecorations": False,
        "textFormat": "Raw",
    }
    
    url = f"{BING_SEARCH_ENDPOINT}?{urllib.parse.urlencode(params)}"
    
    headers = {
        "Ocp-Apim-Subscription-Key": BING_SEARCH_API_KEY,
        "User-Agent": "Mozilla/5.0 (TechnicalSupportAI)",
    }
    
    request = urllib.request.Request(url, headers=headers)
    
    with urllib.request.urlopen(request, timeout=WEB_SEARCH_TIMEOUT) as response:
        data = json.loads(response.read().decode("utf-8"))
    
    results = []
    for item in data.get("webPages", {}).get("value", []):
        results.append({
            "title": item.get("name", ""),
            "url": item.get("url", ""),
            "snippet": item.get("snippet", ""),
        })
    
    logger.info(f"Bing Search returned {len(results)} results")
    return results


def _duckduckgo_search(query: str, count: int) -> List[Dict[str, str]]:
    """
    Fallback search using DuckDuckGo via ddgs library.
    This is more reliable than HTML scraping.
    """
    try:
        from ddgs import DDGS
        
        logger.info(f"DuckDuckGo search starting for query: {query}")
        results = []
        with DDGS() as ddgs:
            # Use text search with max_results parameter
            search_results = list(ddgs.text(query, max_results=count))
            logger.info(f"Raw search returned {len(search_results)} items")
            
            for i, item in enumerate(search_results):
                logger.debug(f"Processing result {i+1}: {item.keys()}")
                result = {
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "snippet": item.get("body", ""),
                }
                # Only add if we have at least a URL
                if result["url"]:
                    results.append(result)
                else:
                    logger.warning(f"Skipping result {i+1} - no URL found")
        
        logger.info(f"DuckDuckGo search processed {len(results)} valid results")
        return results
        
    except ImportError:
        logger.warning("ddgs library not installed, trying duckduckgo-search")
        try:
            from duckduckgo_search import DDGS
            
            results = []
            with DDGS() as ddgs:
                search_results = list(ddgs.text(query, max_results=count))
                
                for item in search_results:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("href", ""),
                        "snippet": item.get("body", ""),
                    })
            
            logger.info(f"DuckDuckGo search (legacy) returned {len(results)} results")
            return results
        except ImportError:
            logger.warning("Neither ddgs nor duckduckgo-search installed, falling back to HTML parsing")
            return _duckduckgo_html_fallback(query, count)
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}", exc_info=True)
        return _duckduckgo_html_fallback(query, count)


def _duckduckgo_html_fallback(query: str, count: int) -> List[Dict[str, str]]:
    """
    Fallback search using DuckDuckGo HTML (less reliable).
    Note: This is a basic implementation and may be rate-limited.
    """
    
    # DuckDuckGo HTML search endpoint
    params = {
        "q": query,
        "kl": "us-en",  # Region
    }
    
    url = f"https://html.duckduckgo.com/html/?{urllib.parse.urlencode(params)}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    }
    
    request = urllib.request.Request(url, headers=headers)
    
    with urllib.request.urlopen(request, timeout=WEB_SEARCH_TIMEOUT) as response:
        html = response.read().decode("utf-8")
    
    # Parse results from HTML
    results = _parse_duckduckgo_html(html, count)
    
    logger.info(f"DuckDuckGo search returned {len(results)} results")
    return results


def _parse_duckduckgo_html(html: str, max_results: int) -> List[Dict[str, str]]:
    """Parse search results from DuckDuckGo HTML."""
    
    results = []
    
    # Simple parsing - look for result links
    # This is basic and may need adjustment based on DuckDuckGo's HTML structure
    lines = html.split('\n')
    
    i = 0
    while i < len(lines) and len(results) < max_results:
        line = lines[i]
        
        # Look for result title links
        if 'class="result__a"' in line or 'class=\'result__a\'' in line:
            # Extract URL
            url_start = line.find('href="')
            if url_start == -1:
                url_start = line.find("href='")
            
            if url_start != -1:
                url_start += 6
                url_end = line.find('"', url_start)
                if url_end == -1:
                    url_end = line.find("'", url_start)
                
                if url_end != -1:
                    url = line[url_start:url_end]
                    # DuckDuckGo wraps URLs in a redirect
                    if url.startswith('//duckduckgo.com/l/?'):
                        url = urllib.parse.unquote(url.split('uddg=')[-1].split('&')[0])
                    
                    # Extract title
                    title_start = line.find('>')
                    title_end = line.find('</a>')
                    title = ""
                    if title_start != -1 and title_end != -1:
                        title = line[title_start + 1:title_end].strip()
                        # Remove HTML tags
                        title = title.replace('<b>', '').replace('</b>', '')
                    
                    # Look for snippet in following lines
                    snippet = ""
                    for j in range(i + 1, min(i + 10, len(lines))):
                        if 'class="result__snippet"' in lines[j]:
                            snippet_line = lines[j]
                            snippet_start = snippet_line.find('>')
                            snippet_end = snippet_line.find('</a>')
                            if snippet_start != -1:
                                if snippet_end == -1:
                                    snippet_end = len(snippet_line)
                                snippet = snippet_line[snippet_start + 1:snippet_end].strip()
                                snippet = snippet.replace('<b>', '').replace('</b>', '')
                                break
                    
                    if url and url.startswith('http'):
                        results.append({
                            "title": title or "Result",
                            "url": url,
                            "snippet": snippet,
                        })
        
        i += 1
    
    return results


def fetch_page_content(url: str, max_length: int = 3000) -> str:
    """
    Fetch and extract readable content from a webpage.
    
    Args:
        url: URL to fetch
        max_length: Maximum length of content to return
        
    Returns:
        Extracted text content
    """
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (TechnicalSupportAI)",
        }
        
        request = urllib.request.Request(url, headers=headers)
        
        with urllib.request.urlopen(request, timeout=WEB_SEARCH_TIMEOUT) as response:
            html = response.read().decode("utf-8", errors="ignore")
        
        # Extract text content
        parser = _ContentExtractor()
        parser.feed(html)
        
        return parser.get_text(max_length)
    
    except Exception as e:
        logger.debug(f"Failed to fetch content from {url}: {e}")
        raise
