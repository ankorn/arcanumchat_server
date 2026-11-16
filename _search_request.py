import time
import asyncio
import logging

API_URL = "https://mfphsrdubggjqxvyuzil.supabase.co/functions/v1/knn";
API_KEY = "sb_publishable_XRNtK6CNXu6R2qOwelRE6w_SqIxMsVP";
RETRIES = 2

async def _search_request(query: str, http_client, logger: logging.Logger) -> dict:
    """Arcanum search call with retry (async)."""
    assert http_client is not None, "http_client not initialized"
    last_exc: Exception | None = None

    for attempt in range(RETRIES + 1):
        t0 = time.monotonic()
        try:
            res = await http_client.post(
                API_URL,
                headers={
                    "Content-Type": "application/json",
                    "apikey": API_KEY,
                },
                json={"query": query},
            )
            elapsed = time.monotonic() - t0
            if not res.is_success:
                raise RuntimeError(
                    f"Search failed: {res.status_code} {res.reason_phrase} after {elapsed:.2f}s"
                )
            logger.info(
                "search_arcanum: HTTP %d in %.2fs (attempt %d)",
                res.status_code, elapsed, attempt + 1,
            )
            return res.json()
        except Exception as exc:
            last_exc = exc
            elapsed = time.monotonic() - t0
            if attempt < RETRIES:
                backoff = 2 ** attempt
                logger.warning(
                    "search_arcanum: attempt %d failed in %.2fs (%s) — retry in %ds",
                    attempt + 1, elapsed, exc, backoff,
                )
                await asyncio.sleep(backoff)
            else:
                logger.error(
                    "search_arcanum: all attempts failed in %.2fs: %s",
                    elapsed, exc,
                )

    assert last_exc is not None
    raise last_exc