"""HTTP-клиент с повторными попытками.

Остальной код работает только с HttpClient/HttpResponse/HttpError, поэтому
requests можно заменить на другую библиотеку, не трогая ничего, кроме этого модуля.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import requests

logger = logging.getLogger(__name__)

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)
# Ограничение сверху на Retry-After, чтобы сайт не мог «усыпить» сервис надолго.
MAX_RETRY_AFTER = 300.0


@dataclass(frozen=True)
class HttpResponse:
    url: str
    status_code: int
    content: bytes
    # Кодировка из заголовка Content-Type, если она там указана.
    encoding: str | None
    headers: dict[str, str]

    @property
    def text(self) -> str:
        return self.content.decode(self.encoding or "utf-8", errors="replace")


class HttpError(Exception):
    def __init__(self, message: str, status_code: int | None = None, transient: bool = True):
        super().__init__(message)
        self.status_code = status_code
        # transient=True — повтор позже может помочь (сеть, 5xx, 429);
        # False — не поможет (404, 403 и т.п.).
        self.transient = transient


def _is_retryable_status(status: int) -> bool:
    return status == 429 or status >= 500


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())


class HttpClient:
    def __init__(
        self,
        timeout: float = 30,
        max_attempts: int = 5,
        backoff_base: float = 1,
        backoff_max: float = 30,
        user_agent: str = DEFAULT_USER_AGENT,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if max_attempts < 1:
            raise ValueError("max_attempts должно быть >= 1")
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        # Позволяет прерывать ожидание между попытками при остановке сервиса.
        self._sleep = sleep
        self._session = requests.Session()
        self._session.headers["User-Agent"] = user_agent

    def get(self, url: str) -> HttpResponse:
        last_error = ""
        for attempt in range(1, self._max_attempts + 1):
            retry_after: float | None = None
            try:
                resp = self._session.get(url, timeout=self._timeout)
            except requests.RequestException as e:
                last_error = f"{type(e).__name__}: {e}"
            else:
                if resp.ok:
                    return HttpResponse(
                        url=resp.url,
                        status_code=resp.status_code,
                        content=resp.content,
                        encoding=requests.utils.get_encoding_from_headers(resp.headers)
                        if "charset" in resp.headers.get("Content-Type", "").lower()
                        else None,
                        headers=dict(resp.headers),
                    )
                if not _is_retryable_status(resp.status_code):
                    raise HttpError(
                        f"GET {url}: HTTP {resp.status_code}",
                        status_code=resp.status_code,
                        transient=False,
                    )
                last_error = f"HTTP {resp.status_code}"
                if resp.status_code == 429:
                    retry_after = _parse_retry_after(resp.headers.get("Retry-After"))

            if attempt == self._max_attempts:
                break
            delay = min(self._backoff_base * 2 ** (attempt - 1), self._backoff_max)
            if retry_after is not None:
                delay = max(delay, min(retry_after, MAX_RETRY_AFTER))
            logger.warning(
                "GET %s: попытка %d/%d не удалась (%s), повтор через %.1f с",
                url, attempt, self._max_attempts, last_error, delay,
            )
            self._sleep(delay)

        raise HttpError(
            f"GET {url}: все {self._max_attempts} попыток не удались, последняя ошибка: {last_error}",
            transient=True,
        )
