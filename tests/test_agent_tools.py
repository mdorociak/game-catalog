import inspect
import json

import httpx
import pytest

from agent.client import CatalogClient
from agent.tools import GAME_FIELDS, HANDLERS, TOOLS, TOOLS_BY_NAME, anthropic_tools, run_tool

HADES = {
    "appid": 1145360, "name": "Hades", "release_date": "2020-09-17", "price": "24.50",
    "is_free": False, "positive": 250000, "negative": 4000, "genres": ["Action", "Indie", "RPG"],
}
BALATRO = {
    "appid": 2379780, "name": "Balatro", "release_date": "2024-02-20", "price": "14.99",
    "is_free": False, "positive": 150000, "negative": 2000, "genres": ["Indie", "Strategy"],
}


class FakeAPI:
    def __init__(self, routes):
        self.routes = routes
        self.requests: list[httpx.Request] = []

    def __call__(self, request):
        self.requests.append(request)
        route = self.routes.get(request.url.path, (404, {"detail": "Not found."}))
        if callable(route):
            return route(request)
        status, body = route
        return httpx.Response(status, json=body)

    @property
    def last_params(self):
        return dict(self.requests[-1].url.params)


def run(api, name, tool_input):
    client = CatalogClient("http://catalog.test/api", transport=httpx.MockTransport(api))
    content, is_error = run_tool(name, tool_input, client)
    return (content if is_error else json.loads(content)), is_error


def page(results, count=None, next_url=None):
    return {"count": len(results) if count is None else count, "next": next_url, "previous": None, "results": results}


def test_search_maps_parameters_to_query_string():
    api = FakeAPI({"/api/games/": (200, page([HADES]))})
    run(api, "search_games", {
        "query": "hades", "tag": "Roguelike", "genre": "Action", "category": "Single-player",
        "min_price": 5, "max_price": 30.5, "is_free": False,
        "released_after": "2020-01-01", "ordering": "-positive",
    })
    assert api.last_params == {
        "search": "hades",
        "tag": "Roguelike", "genre": "Action", "category": "Single-player",
        "min_price": "5", "max_price": "30.5", "is_free": "false",
        "released_after": "2020-01-01", "ordering": "-positive",
    }


@pytest.mark.parametrize("ordering", ["-Positive", "-POSITIVE", "-positive"])
def test_enum_is_matched_case_insensitively(ordering):
    api = FakeAPI({"/api/games/": (200, page([]))})
    _, is_error = run(api, "search_games", {"ordering": ordering})
    assert not is_error
    assert api.last_params == {"ordering": "-positive"}


def test_search_without_filters_sends_no_parameters():
    api = FakeAPI({"/api/games/": (200, page([]))})
    run(api, "search_games", {})
    assert api.last_params == {}


def test_search_trims_fields_and_keeps_total_count():
    api = FakeAPI({"/api/games/": (200, page([HADES, BALATRO], count=57))})
    result, is_error = run(api, "search_games", {"limit": 1})
    assert not is_error
    assert result["count"] == 57
    assert len(result["games"]) == 1
    assert set(result["games"][0]) == set(GAME_FIELDS)


def test_search_with_no_results_suggests_list_tags():
    api = FakeAPI({"/api/games/": (200, page([]))})
    result, is_error = run(api, "search_games", {"tag": "rogue-like"})
    assert not is_error
    assert result["count"] == 0
    assert "list_tags" in result["hint"]


def test_search_rejects_min_price_above_max_price():
    api = FakeAPI({})
    content, is_error = run(api, "search_games", {"min_price": 30, "max_price": 10})
    assert is_error and "min_price" in content
    assert api.requests == []


def test_get_game_keeps_top_10_tag_names():
    tags = [{"name": f"Tag {i}", "votes": 1000 - i} for i in range(15)]
    detail = {**HADES, "required_age": 0, "categories": ["Single-player"], "tags": tags}
    api = FakeAPI({"/api/games/1145360/": (200, detail)})
    result, _ = run(api, "get_game", {"appid": 1145360})
    assert result["tags"] == [f"Tag {i}" for i in range(10)]
    assert result["categories"] == ["Single-player"]
    assert "is_free" not in result


def test_get_game_not_found_is_a_readable_error():
    content, is_error = run(FakeAPI({}), "get_game", {"appid": 123})
    assert is_error
    assert content == "Game 123 not found."


def test_similar_games_passes_limit_and_keeps_shared_tags():
    api = FakeAPI({"/api/games/1145360/similar/": (200, [{**BALATRO, "shared_tags": 2}])})
    result, _ = run(api, "similar_games", {"appid": 1145360, "limit": 3})
    assert api.last_params == {"limit": "3"}
    assert result["games"] == [{**{k: BALATRO[k] for k in GAME_FIELDS}, "shared_tags": 2}]


def test_similar_games_default_limit_is_5():
    api = FakeAPI({"/api/games/1/similar/": (200, [])})
    result, _ = run(api, "similar_games", {"appid": 1})
    assert api.last_params == {"limit": "5"}
    assert "hint" in result


def tag_pages(total):
    def handler(request):
        number = int(request.url.params.get("page", 1))
        rows = [{"id": i, "name": f"Tag {i}", "game_count": 1000 - i}
                for i in range((number - 1) * 20, min(number * 20, total))]
        next_url = f"http://catalog.test/api/tags/?page={number + 1}" if number * 20 < total else None
        return httpx.Response(200, json=page(rows, count=total, next_url=next_url))

    return handler


def test_list_tags_walks_pages_until_limit():
    api = FakeAPI({"/api/tags/": tag_pages(500)})
    result, _ = run(api, "list_tags", {"limit": 45})
    assert len(result["tags"]) == 45
    assert len(api.requests) == 3
    assert list(result["tags"].items())[0] == ("Tag 0", 1000)


def test_list_tags_stops_when_there_are_no_more_pages():
    api = FakeAPI({"/api/tags/": tag_pages(30)})
    result, _ = run(api, "list_tags", {})
    assert len(result["tags"]) == 30
    assert len(api.requests) == 2


def test_get_wishlist():
    items = [{"id": 1, "game": 70, "game_name": "Half-Life", "added_at": "2026-11-26T20:00:00Z"}]
    result, _ = run(FakeAPI({"/api/wishlist/": (200, items)}), "get_wishlist", {})
    assert result == {"count": 1, "games": [{"appid": 70, "name": "Half-Life", "added_at": "2026-11-26T20:00:00Z"}]}


def test_add_to_wishlist():
    item = {"id": 5, "game": 2379780, "game_name": "Balatro", "added_at": "2026-11-26T20:00:00Z"}
    api = FakeAPI({"/api/wishlist/": (201, item)})
    result, is_error = run(api, "add_to_wishlist", {"appid": 2379780})
    assert not is_error
    assert result["added"]["name"] == "Balatro"
    assert api.requests[-1].method == "POST"


@pytest.mark.parametrize("name, tool_input, message", [
    ("delete_everything", {}, "Unknown tool 'delete_everything'"),
    ("get_game", {}, "Missing required parameter(s): appid"),
    ("get_game", {"appid": "70"}, "appid must be of type integer"),
    ("get_game", {"appid": True}, "appid must be of type integer"),
    ("search_games", {"name": "hades"}, "Unknown parameter(s): name"),
    ("search_games", {"limit": 50}, "limit must be at most 20"),
    ("search_games", {"limit": 0}, "limit must be at least 1"),
    ("search_games", {"ordering": "negative"}, "ordering must be one of"),
    ("search_games", {"released_after": "last year"}, "YYYY-MM-DD"),
    ("search_games", "not a dict", "must be a JSON object"),
    ("similar_games", {"appid": 1, "limit": 11}, "limit must be at most 10"),
])
def test_bad_input_is_an_error_message_and_no_request(name, tool_input, message):
    api = FakeAPI({})
    content, is_error = run(api, name, tool_input)
    assert is_error
    assert message in content
    assert api.requests == []


def test_null_optional_parameters_are_ignored():

    api = FakeAPI({"/api/games/": (200, page([]))})
    _, is_error = run(api, "search_games", {"tag": None, "limit": None})
    assert not is_error
    assert api.last_params == {}


def test_api_down_is_an_error_message():
    def handler(request):
        raise httpx.ConnectError("Connection refused", request=request)

    content, is_error = run(handler, "search_games", {"query": "hades"})
    assert is_error
    assert "not reachable" in content


def test_unexpected_api_shape_is_an_error_message():

    content, is_error = run(FakeAPI({"/api/games/": (200, {"oops": True})}), "search_games", {})
    assert is_error
    assert "failed unexpectedly" in content


def test_every_tool_has_a_handler_with_matching_parameters():
    assert TOOLS_BY_NAME.keys() == HANDLERS.keys()
    for name, tool in TOOLS_BY_NAME.items():
        schema = tool["input_schema"]
        parameters = list(inspect.signature(HANDLERS[name]).parameters.values())[1:]
        assert {p.name for p in parameters} == set(schema["properties"]), name
        required = {p.name for p in parameters if p.default is inspect.Parameter.empty}
        assert required == set(schema["required"]), name


def test_prices_are_described_as_usd():
    for name in ("search_games", "similar_games"):
        assert "USD" in TOOLS_BY_NAME[name]["description"], name
    properties = TOOLS_BY_NAME["search_games"]["input_schema"]["properties"]
    assert "USD" in properties["min_price"]["description"]
    assert "USD" in properties["max_price"]["description"]


def test_default_definitions_are_not_strict_and_keep_the_full_schema():
    definitions = anthropic_tools()
    assert [d["name"] for d in definitions] == [t["name"] for t in TOOLS]
    for definition, tool in zip(definitions, TOOLS):
        assert "strict" not in definition
        assert definition["input_schema"] == tool["input_schema"]
    limit = definitions[0]["input_schema"]["properties"]["limit"]
    assert (limit["minimum"], limit["maximum"]) == (1, 20)


def test_strict_definitions_fit_the_api_limits():
    definitions = anthropic_tools(strict=True)
    assert [d["name"] for d in definitions] == [t["name"] for t in TOOLS]
    optional = 0
    for definition in definitions:
        schema = definition["input_schema"]
        assert definition["strict"] is True
        assert schema["additionalProperties"] is False
        for rules in schema["properties"].values():
            assert "minimum" not in rules and "maximum" not in rules
        optional += len(set(schema["properties"]) - set(schema["required"]))
    assert optional <= 24


def test_ranges_are_moved_into_descriptions():
    limit = anthropic_tools(strict=True)[0]["input_schema"]["properties"]["limit"]
    assert "maximum: 20" in limit["description"]


def test_exclude_removes_a_tool():
    names = [d["name"] for d in anthropic_tools(exclude=frozenset({"list_tags"}))]
    assert "list_tags" not in names
