
import json

import httpx
import pytest

from agent.client import CatalogClient, CatalogError

BASE = "http://catalog.test/api"


def make_client(handler, token=None):
    return CatalogClient(BASE, token=token, transport=httpx.MockTransport(handler))


def respond(status, body=None):
    return lambda request: httpx.Response(status, json=body)


def test_paths_are_joined_onto_the_api_prefix():
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={})

    client = make_client(handler)
    client.get_game(70)
    client.similar_games(70, limit=3)
    assert seen == ["/api/games/70/", "/api/games/70/similar/"]


def test_token_goes_in_the_authorization_header():
    headers = []

    def handler(request):
        headers.append(request.headers.get("Authorization"))
        return httpx.Response(200, json=[])

    make_client(handler, token="abc123").get_wishlist()
    make_client(handler).get_wishlist()
    assert headers == ["Token abc123", None]


def test_add_to_wishlist_posts_the_game_id():
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(201, json={"id": 1, "game": 70, "game_name": "Half-Life", "added_at": "x"})

    make_client(handler).add_to_wishlist(70)
    assert requests[0].method == "POST"
    assert requests[0].url.path == "/api/wishlist/"
    assert json.loads(requests[0].content) == {"game": 70}



def test_404_names_the_game():
    with pytest.raises(CatalogError, match=r"^Game 123 not found\.$"):
        make_client(respond(404, {"detail": "No Game matches the given query."})).get_game(123)


def test_unknown_game_on_wishlist_add_is_not_found():
    body = {"game": ['Invalid pk "999" - object does not exist.']}
    with pytest.raises(CatalogError, match="Game 999 not found"):
        make_client(respond(400, body)).add_to_wishlist(999)


def test_duplicate_wishlist_add():
    body = {"non_field_errors": ["This game is already on your wishlist."]}
    with pytest.raises(CatalogError, match="already on the wishlist"):
        make_client(respond(400, body)).add_to_wishlist(70)


def test_other_400_shows_drf_field_errors():
    body = {"released_after": ["Enter a valid date."]}
    with pytest.raises(CatalogError, match="released_after: Enter a valid date."):
        make_client(respond(400, body)).list_games({"released_after": "nope"})


@pytest.mark.parametrize("status", [401, 403])
def test_auth_failure_points_at_the_token(status):
    with pytest.raises(CatalogError, match="GAME_CATALOG_TOKEN"):
        make_client(respond(status, {"detail": "Invalid token."})).get_wishlist()


def test_server_error():
    with pytest.raises(CatalogError, match="server error 500"):
        make_client(lambda request: httpx.Response(500, text="boom")).get_game(1)


def test_invalid_json():
    with pytest.raises(CatalogError, match="not valid JSON"):
        make_client(lambda request: httpx.Response(200, text="<html>")).get_game(1)


def broken_gzip(request):
    return httpx.Response(200, content=b"not gzip", headers={"Content-Encoding": "gzip"})


def raising(error_class, message):
    def handler(request):
        raise error_class(message, request=request)

    return handler


def test_connection_refused_asks_if_the_server_is_running():
    with pytest.raises(CatalogError, match=r"not reachable at http://catalog\.test/api\. Is the server running\?") as caught:
        make_client(raising(httpx.ConnectError, "Connection refused")).get_game(1)
    assert isinstance(caught.value.__cause__, httpx.ConnectError)


@pytest.mark.parametrize("handler, original", [
    (broken_gzip, httpx.DecodingError),
    (raising(httpx.TooManyRedirects, "Exceeded maximum allowed redirects."), httpx.TooManyRedirects),
    (raising(httpx.RemoteProtocolError, "Server disconnected"), httpx.RemoteProtocolError),
])
def test_other_request_failure_names_the_error(handler, original):
    with pytest.raises(CatalogError) as caught:
        make_client(handler).get_game(1)
    assert str(caught.value) == f"Request to the catalog API at http://catalog.test/api failed ({original.__name__})."
    assert isinstance(caught.value.__cause__, original)


@pytest.mark.parametrize("error_class", [httpx.ReadTimeout, httpx.ConnectTimeout])
def test_timeout(error_class):
    with pytest.raises(CatalogError, match="did not respond within 10s") as caught:
        make_client(raising(error_class, "timed out")).get_game(1)
    assert isinstance(caught.value.__cause__, error_class)


def test_from_env(monkeypatch):
    monkeypatch.setenv("GAME_CATALOG_URL", "http://web:8000/api/")
    monkeypatch.setenv("GAME_CATALOG_TOKEN", "secret")
    client = CatalogClient.from_env()
    assert client.base_url == "http://web:8000/api"
    assert client._http.headers["Authorization"] == "Token secret"
