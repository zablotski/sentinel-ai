"""Classify UNKNOWN license texts against canonical SPDX signatures.

Uses sentence-transformers cosine similarity in-process (no Qdrant round-trip)
so it works in CI and degrades gracefully when embeddings are unavailable.
"""

import logging

from app.services.license_signatures import LICENSE_SIGNATURES

logger = logging.getLogger("sentinel.license_classifier")

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
MAX_CLASSIFIED_CHARS = 5000

_encoder = None
_signature_matrix = None
_load_failed = False


def _get_encoder():
    global _encoder, _load_failed
    if _encoder is not None or _load_failed:
        return _encoder
    try:
        from sentence_transformers import SentenceTransformer

        _encoder = SentenceTransformer(EMBEDDING_MODEL_NAME)
        logger.info("License classifier encoder ready: %s", EMBEDDING_MODEL_NAME)
    except Exception as err:
        _load_failed = True
        logger.warning("License classifier unavailable (%s); UNKNOWN stays unresolved", err)
        _encoder = None
    return _encoder


def _get_signature_matrix():
    global _signature_matrix
    if _signature_matrix is not None:
        return _signature_matrix
    encoder = _get_encoder()
    if encoder is None:
        return None
    try:
        texts = list(LICENSE_SIGNATURES.values())
        _signature_matrix = encoder.encode(texts, normalize_embeddings=True)
    except Exception as err:
        logger.warning("Failed to embed license signatures: %s", err)
        _signature_matrix = None
    return _signature_matrix


def classify_license_text(license_text: str) -> tuple[str, float] | None:
    """Return (spdx_id, cosine_score) of the closest canonical license, or None."""
    if not license_text or not license_text.strip():
        return None

    matrix = _get_signature_matrix()
    if matrix is None:
        return None

    encoder = _get_encoder()
    try:
        import numpy as np

        vector = encoder.encode(
            license_text[:MAX_CLASSIFIED_CHARS], normalize_embeddings=True
        )
        scores = np.dot(matrix, vector)
        best_index = int(np.argmax(scores))
        spdx_ids = list(LICENSE_SIGNATURES.keys())
        return spdx_ids[best_index], float(scores[best_index])
    except Exception as err:
        logger.warning("License classification failed: %s", err)
        return None
