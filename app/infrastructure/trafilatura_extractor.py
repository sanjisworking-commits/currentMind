"""Trafilatura-based article content extractor.

Implements `ArticleExtractor` by downloading a page over HTTP with `httpx`
and extracting the main article text with Trafilatura. Expected operational
failures (network errors, unsupported pages, insufficient content, unexpected
extraction failures) are represented as `ExtractedArticle` status values.
An invalid `url` argument is a caller contract violation and raises
`ValueError` before any HTTP request is made, because `ExtractedArticle.url`
only accepts valid absolute HTTP/HTTPS URLs.
"""

import logging
import re
from urllib.parse import urlparse

import httpx
import trafilatura

from app.domain.extraction import ExtractedArticle, ExtractionStatus

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_MIN_CONTENT_LENGTH = 200
DEFAULT_MAX_RESPONSE_BYTES = 10_000_000
USER_AGENT = "CurrentMind/0.1 (+personal UPSC study tool)"

_SUPPORTED_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})

# Magic-byte prefixes for common binary formats, used only when a response
# omits Content-Type entirely and we must guess whether the body is HTML.
_BINARY_SIGNATURES: tuple[bytes, ...] = (
    b"%PDF-",
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",
    b"GIF87a",
    b"GIF89a",
)

_TRANSIENT_STATUS_CODES = frozenset({408, 429})

_BLANK_LINE_RUN = re.compile(r"\n{3,}")


class _HttpStatusFailure(Exception):
    """Raised internally when the response status code indicates failure."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"HTTP {status_code}")
        self.status_code = status_code


class _ResponseTooLarge(Exception):
    """Raised internally when the response body exceeds the configured cap."""


def _validate_url(value: str) -> str:
    """Validate and normalize an article URL before any HTTP request.

    Raises:
        ValueError: if `value` is not a string, or is not a non-blank
            absolute http(s) URL with a network location.
    """
    if not isinstance(value, str):
        raise ValueError(f"url must be a string, got {type(value).__name__}")
    cleaned = value.strip()
    parsed = urlparse(cleaned)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"url must use the http or https scheme, got: {value!r}")
    if not parsed.netloc:
        raise ValueError(f"url must include a network location, got: {value!r}")
    return cleaned


def _is_transient_status(status_code: int) -> bool:
    return status_code in _TRANSIENT_STATUS_CODES or status_code >= 500


def _looks_binary(body: bytes) -> bool:
    return any(body.startswith(signature) for signature in _BINARY_SIGNATURES)


def _content_type_supported(content_type: str, body: bytes) -> bool:
    """Decide whether a response should be handed to Trafilatura.

    A recognized HTML content type is always accepted. A missing content
    type is tentatively accepted unless the body starts with a known binary
    signature. Any other explicit content type is rejected.
    """
    main_type = content_type.split(";", 1)[0].strip().lower()
    if main_type in _SUPPORTED_CONTENT_TYPES:
        return True
    if main_type == "":
        return not _looks_binary(body)
    return False


def _clean_text(text: str) -> str:
    """Normalize whitespace without altering paragraph content or order."""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in normalized.split("\n")]
    normalized = "\n".join(lines)
    collapsed = _BLANK_LINE_RUN.sub("\n\n", normalized)
    return collapsed.strip("\n")


class TrafilaturaArticleExtractor:
    """Extracts clean article text from a URL using Trafilatura."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        min_content_length: int = DEFAULT_MIN_CONTENT_LENGTH,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero")
        if min_content_length <= 0:
            raise ValueError("min_content_length must be greater than zero")
        if max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be greater than zero")
        self._timeout_seconds = timeout_seconds
        self._min_content_length = min_content_length
        self._max_response_bytes = max_response_bytes
        self._transport = transport

    def extract(self, url: str) -> ExtractedArticle:
        """Download and extract clean article content from `url`.

        Raises:
            ValueError: if `url` is not a non-blank, absolute http(s) URL
                with a network location. No HTTP request is made in this case.
        """
        validated_url = _validate_url(url)
        logger.info("Extraction started url=%s", validated_url)

        try:
            final_url, content_type, body = self._fetch(validated_url)
        except httpx.TimeoutException:
            reason = f"Timed out fetching {validated_url}"
            logger.error("Extraction network failure (timeout) url=%s", validated_url)
            return ExtractedArticle(
                url=validated_url, status=ExtractionStatus.NETWORK_ERROR, error_reason=reason
            )
        except _HttpStatusFailure as exc:
            reason = f"{validated_url} returned HTTP {exc.status_code}"
            if _is_transient_status(exc.status_code):
                logger.error(
                    "Extraction network failure (status) url=%s status=%d",
                    validated_url,
                    exc.status_code,
                )
                return ExtractedArticle(
                    url=validated_url, status=ExtractionStatus.NETWORK_ERROR, error_reason=reason
                )
            logger.warning(
                "Extraction rejected (status) url=%s status=%d", validated_url, exc.status_code
            )
            return ExtractedArticle(
                url=validated_url, status=ExtractionStatus.UNSUPPORTED_PAGE, error_reason=reason
            )
        except _ResponseTooLarge as exc:
            reason = str(exc)
            logger.warning(
                "Extraction rejected (oversized response) url=%s reason=%s",
                validated_url,
                reason,
            )
            return ExtractedArticle(
                url=validated_url, status=ExtractionStatus.UNSUPPORTED_PAGE, error_reason=reason
            )
        except httpx.HTTPError as exc:
            reason = f"Failed to fetch {validated_url}: {exc}"
            logger.error("Extraction network failure url=%s error=%s", validated_url, exc)
            return ExtractedArticle(
                url=validated_url, status=ExtractionStatus.NETWORK_ERROR, error_reason=reason
            )

        logger.info(
            "Page fetch completed url=%s final_url=%s content_type=%s bytes=%d",
            validated_url,
            final_url,
            content_type,
            len(body),
        )

        if not _content_type_supported(content_type, body):
            reason = f"Unsupported content type: {content_type!r}"
            logger.warning(
                "Extraction rejected (content type) url=%s reason=%s", validated_url, reason
            )
            return ExtractedArticle(
                url=validated_url, status=ExtractionStatus.UNSUPPORTED_PAGE, error_reason=reason
            )

        try:
            raw_text = trafilatura.extract(
                body,
                url=final_url,
                output_format="txt",
                include_comments=False,
                include_links=False,
                include_images=False,
            )
            cleaned = _clean_text(raw_text) if raw_text else ""
        except Exception as exc:
            logger.error("Unexpected extraction failure url=%s", validated_url, exc_info=True)
            return ExtractedArticle(
                url=validated_url,
                status=ExtractionStatus.UNEXPECTED_ERROR,
                error_reason=f"Unexpected extraction failure: {type(exc).__name__}",
            )

        if not cleaned:
            logger.warning("Insufficient extracted content url=%s chars=0", validated_url)
            return ExtractedArticle(
                url=validated_url,
                status=ExtractionStatus.INSUFFICIENT_CONTENT,
                error_reason="Trafilatura returned no extractable content",
            )

        if len(cleaned) < self._min_content_length:
            reason = (
                f"Extracted text below minimum length "
                f"({len(cleaned)} < {self._min_content_length} characters)"
            )
            logger.warning(
                "Insufficient extracted content url=%s chars=%d min=%d",
                validated_url,
                len(cleaned),
                self._min_content_length,
            )
            return ExtractedArticle(
                url=validated_url,
                status=ExtractionStatus.INSUFFICIENT_CONTENT,
                text=cleaned,
                error_reason=reason,
            )

        logger.info(
            "Trafilatura extraction completed url=%s chars=%d", validated_url, len(cleaned)
        )
        return ExtractedArticle(url=validated_url, status=ExtractionStatus.SUCCESS, text=cleaned)

    def _fetch(self, url: str) -> tuple[str, str, bytes]:
        """Stream the response body, enforcing the response-size cap while reading.

        Returns:
            A tuple of (final URL after redirects, Content-Type header value
            or empty string, response body bytes).

        Raises:
            httpx.TimeoutException: on request timeout.
            httpx.HTTPError: on connection or other transport failure.
            _HttpStatusFailure: if the final response status code is outside
                the 200-299 range (including a non-followable 3xx, such as a
                redirect with no Location header, or a 304).
            _ResponseTooLarge: if the declared or streamed body size exceeds
                `max_response_bytes`.
        """
        headers = {"User-Agent": USER_AGENT}
        with httpx.Client(
            timeout=self._timeout_seconds,
            follow_redirects=True,
            transport=self._transport,
            headers=headers,
        ) as client:
            with client.stream("GET", url) as response:
                if not 200 <= response.status_code < 300:
                    raise _HttpStatusFailure(response.status_code)

                content_length = response.headers.get("content-length")
                if content_length is not None:
                    try:
                        declared_length = int(content_length)
                    except ValueError:
                        declared_length = None
                    if declared_length is not None and declared_length > self._max_response_bytes:
                        raise _ResponseTooLarge(
                            f"Declared response size {declared_length} bytes exceeds "
                            f"limit of {self._max_response_bytes} bytes"
                        )

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_bytes():
                    total += len(chunk)
                    if total > self._max_response_bytes:
                        raise _ResponseTooLarge(
                            f"Response size exceeds limit of {self._max_response_bytes} bytes"
                        )
                    chunks.append(chunk)

                body = b"".join(chunks)
                content_type = response.headers.get("content-type", "")
                final_url = str(response.url)

        return final_url, content_type, body
