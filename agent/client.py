import os
from typing import Any

import httpx

DEFAULT_TIMEOUT = 10


class CatalogError(Exception):
    """Anything that went wrong while talking to the catalog API."""


class CatalogClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
        transport: httpx.BaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        headers = {"Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Token {token}"
        self._http = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
            transport=transport,
        )

    @classmethod
    def from_env(cls) -> "CatalogClient":
        return cls(
            base_url=os.environ.get("GAME_CATALOG_URL", "http://localhost:8000/api"),
            token=os.environ.get("GAME_CATALOG_TOKEN") or None,
        )

    def close(self) -> None:
        self._http.close()

    def list_games(self, params: dict[str, Any]) -> dict:
        return self._request("GET", "games/", params=params)

    def get_game(self, appid: int) -> dict:
        return self._request(
            "GET", f"games/{appid}/", not_found=f"Game {appid} not found."
        )

    def similar_games(self, appid: int, limit: int) -> list[dict]:
        return self._request(
            "GET",
            f"games/{appid}/similar/",
            params={"limit": limit},
            not_found=f"Game {appid} not found.",
        )

    def list_tags(self, page: int = 1) -> dict:
        return self._request("GET", "tags/", params={"page": page})

    def get_wishlist(self) -> list[dict]:
        return self._request("GET", "wishlist/")

    def add_to_wishlist(self, appid: int) -> dict:
        response = self._send("POST", "wishlist/", json={"game": appid})
        if response.status_code == 400:
            errors = _json_or_none(response) or {}
            if "game" in errors:
                raise CatalogError(f"Game {appid} not found.")
            if "non_field_errors" in errors:
                raise CatalogError(f"Game {appid} is already on the wishlist.")
        return self._parse(response)

    def _request(self, method: str, path: str, *, not_found: str | None = None, **kwargs) -> Any:
        response = self._send(method, path, **kwargs)
        if response.status_code == 404 and not_found:
            raise CatalogError(not_found)
        return self._parse(response)

    def _send(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            return self._http.request(method, path, **kwargs)
        except httpx.TimeoutException as error:
            raise CatalogError(
                f"Catalog API at {self.base_url} did not respond within {self.timeout}s."
            ) from error
        except httpx.ConnectError as error:
            raise CatalogError(
                f"Catalog API is not reachable at {self.base_url}. Is the server running?"
            ) from error
        except httpx.RequestError as error:
            raise CatalogError(
                f"Request to the catalog API at {self.base_url} failed ({type(error).__name__})."
            ) from error

    def _parse(self, response: httpx.Response) -> Any:
        status = response.status_code
        if status in (401, 403):
            raise CatalogError(
                f"Catalog API refused access ({status}). Check GAME_CATALOG_TOKEN."
            )
        if status == 404:
            raise CatalogError(f"Not found: {response.request.url.path}")
        if 400 <= status < 500:
            raise CatalogError(f"Catalog API rejected the request: {_drf_errors(response)}")
        if status >= 500:
            raise CatalogError(f"Catalog API failed with server error {status}.")
        data = _json_or_none(response)
        if data is None:
            raise CatalogError("Catalog API returned a response that is not valid JSON.")
        return data


def _json_or_none(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def _drf_errors(response: httpx.Response) -> str:
    body = _json_or_none(response)
    if isinstance(body, dict):
        if "detail" in body:
            return str(body["detail"])
        parts = []
        for field, messages in body.items():
            if isinstance(messages, list):
                messages = " ".join(str(m) for m in messages)
            parts.append(f"{field}: {messages}")
        return "; ".join(parts)
    return f"HTTP {response.status_code}"
