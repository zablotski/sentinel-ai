import asyncio
import logging
import uuid
from dataclasses import dataclass

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.exceptions import UnexpectedResponse
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.core.config import ModelConfig

logger = logging.getLogger("sentinel.qdrant")

VERDICT_CACHE_COLLECTION = "verdict_cache"
VERDICT_CACHE_VECTOR_SIZE = 1
DUMMY_VECTOR = [0.0]

_client: AsyncQdrantClient | None = None
_verdict_cache_ready = False
_ensure_collection_lock = asyncio.Lock()
_ci_mode = False


def set_ci_mode(enabled: bool = True) -> None:
    """Bypass Qdrant network calls when running without a vector DB (CI runners)."""
    global _ci_mode
    _ci_mode = enabled
    if enabled:
        logger.info("Qdrant CI mode enabled — verdict cache disabled")


def is_ci_mode() -> bool:
    return _ci_mode


@dataclass
class ScoredPoint:
    id: int
    payload: dict


def _get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(url=ModelConfig.QDRANT_HOST)
    return _client


async def _ensure_verdict_cache_collection() -> None:
    if _ci_mode:
        return

    global _verdict_cache_ready
    if _verdict_cache_ready:
        return

    async with _ensure_collection_lock:
        if _verdict_cache_ready:
            return

        client = _get_client()
        try:
            if await client.collection_exists(VERDICT_CACHE_COLLECTION):
                _verdict_cache_ready = True
                return

            await client.create_collection(
                collection_name=VERDICT_CACHE_COLLECTION,
                vectors_config=VectorParams(
                    size=VERDICT_CACHE_VECTOR_SIZE,
                    distance=Distance.COSINE,
                ),
            )
            logger.info("Created Qdrant collection: %s", VERDICT_CACHE_COLLECTION)
            _verdict_cache_ready = True
        except UnexpectedResponse as err:
            if err.status_code == 409:
                logger.info(
                    "Qdrant collection %s already exists (concurrent create).",
                    VERDICT_CACHE_COLLECTION,
                )
                _verdict_cache_ready = True
                return
            logger.exception("Failed to initialize verdict_cache collection: %s", err)
            raise
        except Exception as err:
            logger.exception("Failed to initialize verdict_cache collection: %s", err)
            raise


def _cache_point_id(package_name: str, license_name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{package_name}:{license_name}"))


async def get_cached_verdict(package_name: str, license_name: str) -> dict | None:
    if _ci_mode:
        return None

    if not package_name or not license_name:
        return None

    try:
        await _ensure_verdict_cache_collection()
        client = _get_client()

        records, _ = await client.scroll(
            collection_name=VERDICT_CACHE_COLLECTION,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="package_name",
                        match=MatchValue(value=package_name),
                    ),
                    FieldCondition(
                        key="license_name",
                        match=MatchValue(value=license_name),
                    ),
                ]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )

        if not records:
            return None

        payload = records[0].payload or {}
        verdict = payload.get("verdict")
        reasoning = payload.get("reasoning")
        if not verdict or not reasoning:
            return None

        return {
            "verdict": str(verdict),
            "reasoning": str(reasoning),
        }
    except Exception as err:
        logger.warning(
            "Verdict cache lookup failed for %s (%s): %s",
            package_name,
            license_name,
            err,
        )
        return None


async def save_verdict_to_cache(
    package_name: str,
    license_name: str,
    verdict: str,
    reasoning: str,
) -> None:
    if _ci_mode:
        return

    if not package_name or not license_name or not verdict:
        return

    try:
        await _ensure_verdict_cache_collection()
        client = _get_client()

        point = PointStruct(
            id=_cache_point_id(package_name, license_name),
            vector=DUMMY_VECTOR,
            payload={
                "package_name": package_name,
                "license_name": license_name,
                "verdict": verdict,
                "reasoning": reasoning,
            },
        )
        await client.upsert(collection_name=VERDICT_CACHE_COLLECTION, points=[point])
        logger.info("Cached verdict for %s (%s): %s", package_name, license_name, verdict)
    except Exception as err:
        logger.warning(
            "Verdict cache save failed for %s (%s): %s",
            package_name,
            license_name,
            err,
        )


async def search_policy(query_text: str) -> list[ScoredPoint]:
    _ = query_text
    return [
        ScoredPoint(
            id=1,
            payload={
                "text": "Permissive licenses like MIT, BSD, and Apache 2.0 are SAFE for commercial use."
            },
        ),
        ScoredPoint(
            id=2,
            payload={
                "text": (
                    "Any license that requires the source code of derivative works to be made public "
                    "(e.g. Copyleft, GPL, AGPL) is strictly FORBIDDEN."
                )
            },
        ),
        ScoredPoint(
            id=3,
            payload={
                "text": (
                    "Licenses that restrict commercial use, SaaS deployment, "
                    "or paid redistribution are FORBIDDEN."
                )
            },
        ),
    ]
