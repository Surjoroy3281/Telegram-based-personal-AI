"""Free web search - no API key, no cost. Uses the `ddgs` package (the
successor to `duckduckgo_search`, which was renamed).

DuckDuckGo's unofficial backend rate-limits fairly aggressively and
sometimes just needs a few seconds' breathing room, so this retries a
couple of times with a short delay before giving up.
"""
import logging
import time

from ddgs import DDGS

logger = logging.getLogger(__name__)


def search_web(query: str, max_results: int = 5, retries: int = 3) -> list[dict]:
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=max_results))
            if results:
                return results
            logger.warning("Search for %r returned no results (attempt %d/%d)", query, attempt, retries)
        except Exception as e:
            last_error = e
            logger.warning(
                "Search for %r failed on attempt %d/%d: %s", query, attempt, retries, e
            )
        if attempt < retries:
            time.sleep(2 * attempt)  # 2s, then 4s - DDG's rate limit often clears quickly

    if last_error:
        logger.error("Search for %r failed after %d attempts: %s", query, retries, last_error)
    return []
