from datetime import date

import pytest

from catalog.models import Game, Genre
from tests.factories import make_game

pytestmark = pytest.mark.django_db


@pytest.fixture
def catalog():
    make_game(1, "Hades", price="24.50", release_date=date(2020, 9, 17),
              positive=250000, negative=4000,
              genres=["RPG", "Action", "Indie"], categories=["Single-player"],
              tags={"Action": 400, "Roguelike": 500, "Indie": 300})
    make_game(2, "Counter-Strike", price="9.99", release_date=date(2000, 11, 1),
              positive=124534, genres=["Action"], categories=["Multi-player"],
              tags={"FPS": 800, "Action": 900})
    make_game(3, "Dota 2", price="0", release_date=date(2013, 7, 9),
              positive=1500000, genres=["Free To Play", "Strategy"],
              categories=["Multi-player"], tags={"MOBA": 700})
    make_game(4, "Mystery", price=None, release_date=None, positive=0)
    make_game(5, "Half-Life", price="9.99", release_date=date(1998, 11, 8),
              positive=27755, genres=["Action"], categories=["Single-player"],
              tags={"FPS": 600, "Classic": 500})


def appids(response):
    assert response.status_code == 200, response.content
    return [game["appid"] for game in response.json()["results"]]


# -- list ---------------------------------------------------------------------

def test_list_item_shape(api, catalog):
    hades = api.get("/api/games/").json()["results"][0]
    assert hades == {
        "appid": 1,
        "name": "Hades",
        "release_date": "2020-09-17",
        "price": "24.50",
        "is_free": False,
        "positive": 250000,
        "negative": 4000,
        "genres": ["Action", "Indie", "RPG"],  # names, alphabetical
    }


def test_unknown_price_is_null_and_not_free(api, catalog):
    mystery = api.get("/api/games/4/").json()
    assert mystery["price"] is None
    assert mystery["is_free"] is False
    assert mystery["release_date"] is None


def test_list_is_paginated_by_20(api):
    for appid in range(1, 26):
        make_game(appid, f"Game {appid}")

    first = api.get("/api/games/").json()
    assert set(first) == {"count", "next", "previous", "results"}
    assert first["count"] == 25
    assert len(first["results"]) == 20
    assert first["previous"] is None and first["next"] is not None

    second = api.get("/api/games/", {"page": 2}).json()
    assert [g["appid"] for g in second["results"]] == list(range(21, 26))
    assert second["next"] is None


def test_default_order_is_by_appid(api, catalog):
    assert appids(api.get("/api/games/")) == [1, 2, 3, 4, 5]


# -- detail -------------------------------------------------------------------

def test_detail_shape(api, catalog):
    assert api.get("/api/games/1/").json() == {
        "appid": 1,
        "name": "Hades",
        "release_date": "2020-09-17",
        "price": "24.50",
        "is_free": False,
        "positive": 250000,
        "negative": 4000,
        "genres": ["Action", "Indie", "RPG"],
        "required_age": 0,
        "categories": ["Single-player"],
        "tags": [  # most votes first
            {"name": "Roguelike", "votes": 500},
            {"name": "Action", "votes": 400},
            {"name": "Indie", "votes": 300},
        ],
    }


@pytest.mark.parametrize("url", ["/api/games/999/", "/api/games/abc/"])
def test_unknown_game_is_404(api, catalog, url):
    assert api.get(url).status_code == 404


@pytest.mark.parametrize("method, url", [
    ("post", "/api/games/"),
    ("put", "/api/games/1/"),
    ("patch", "/api/games/1/"),
    ("delete", "/api/games/1/"),
    ("post", "/api/genres/"),
])
def test_writes_are_not_allowed(api, catalog, method, url):
    assert getattr(api, method)(url, {}).status_code == 405
    assert Game.objects.filter(appid=1).exists()


# -- lookups ------------------------------------------------------------------

@pytest.mark.parametrize("url, expected", [
    ("/api/genres/", [("Action", 3), ("Free To Play", 1), ("Indie", 1), ("RPG", 1), ("Strategy", 1)]),
    ("/api/categories/", [("Multi-player", 2), ("Single-player", 2)]),
    ("/api/tags/", [("Action", 2), ("FPS", 2), ("Classic", 1), ("Indie", 1), ("MOBA", 1), ("Roguelike", 1)]),
])
def test_lookups_most_games_first_ties_alphabetical(api, catalog, url, expected):
    data = api.get(url).json()
    assert data["count"] == len(expected)
    assert [(r["name"], r["game_count"]) for r in data["results"]] == expected
    assert set(data["results"][0]) == {"id", "name", "game_count"}


def test_lookup_without_games_has_count_zero(api, catalog):
    Genre.objects.create(name="Unused")
    last = api.get("/api/genres/").json()["results"][-1]
    assert (last["name"], last["game_count"]) == ("Unused", 0)


# -- filters ------------------------------------------------------------------

@pytest.mark.parametrize("params, expected", [
    ({"genre": "action"}, [1, 2, 5]),       
    ({"genre": "INDIE"}, [1]),
    ({"genre": "Act"}, []),                 
    ({"category": "multi-player"}, [2, 3]),
    ({"tag": "fps"}, [2, 5]),
    ({"min_price": "9.99"}, [1, 2, 5]),    
    ({"max_price": "9.99"}, [2, 3, 5]),     
    ({"min_price": "5", "max_price": "10"}, [2, 5]),
    ({"is_free": "true"}, [3]),
    ({"is_free": "false"}, [1, 2, 5]),    
    ({"released_after": "2000-11-01"}, [1, 2, 3]),  
    ({"released_before": "2000-11-01"}, [2, 5]),   
    ({"released_after": "1999-01-01", "released_before": "2015-01-01"}, [2, 3]),
    ({"search": "HALF"}, [5]),          
    ({"search": "a"}, [1, 3, 5]),
    ({"tag": "fps", "genre": "action"}, [2, 5]),
    ({"tag": "fps", "genre": "action", "max_price": "10", "released_after": "2000-01-01"}, [2]),
    ({"genre": "action", "category": "single-player", "tag": "action"}, [1]),
])
def test_filters(api, catalog, params, expected):
    assert appids(api.get("/api/games/", params)) == expected


def test_filters_never_return_duplicates(api):
    make_game(1, "Twice", genres=["Action", "action"], tags={"FPS": 5, "fps": 3})
    make_game(2, "Once", genres=["Action"], tags={"FPS": 1})

    response = api.get("/api/games/", {"tag": "fps", "genre": "ACTION"})
    assert appids(response) == [1, 2]
    assert response.json()["count"] == 2


@pytest.mark.parametrize("params", [
    {"min_price": "cheap"},
    {"max_price": "1,5"},
    {"released_after": "2020-13-45"},
    {"released_before": "yesterday"},
])
def test_invalid_filter_value_is_400(api, catalog, params):
    response = api.get("/api/games/", params)
    assert response.status_code == 400
    assert set(response.json()) == set(params) 


# -- ordering -----------------------------------------------------------------

@pytest.mark.parametrize("ordering, expected", [
    ("name", [2, 3, 1, 5]),
    ("-name", [5, 1, 3, 2]),
    ("release_date", [5, 2, 3, 1]),
    ("-release_date", [1, 3, 2, 5]),
    ("price", [3, 2, 5, 1]),  
    ("-price", [1, 2, 5, 3]),     
    ("positive", [5, 2, 1, 3]),
    ("-positive", [3, 1, 2, 5]),
])
def test_ordering(api, catalog, ordering, expected):
    assert appids(api.get("/api/games/", {"ordering": ordering, "min_price": "0"})) == expected


def test_unknown_ordering_field_is_ignored(api, catalog):
    assert appids(api.get("/api/games/", {"ordering": "negative"})) == [1, 2, 3, 4, 5]


def test_pages_never_overlap_when_sort_key_ties(api):
    for appid in range(1, 46):
        make_game(appid, f"Game {appid}", price="0")

    seen = []
    for page in (1, 2, 3):
        seen += appids(api.get("/api/games/", {"ordering": "price", "page": page}))
    assert seen == list(range(1, 46))


# -- query counts -------------------------------------------------------------

@pytest.fixture
def many_games():
    for appid in range(1, 41):
        make_game(appid, f"Game {appid}", genres=["Action", "Indie", f"G{appid % 5}"],
                  categories=["Single-player", f"C{appid % 3}"],
                  tags={"FPS": appid, "Action": 2 * appid, f"T{appid % 7}": 3})


@pytest.mark.parametrize("params", [
    {},
    {"genre": "action", "tag": "fps", "category": "single-player",
     "search": "game", "ordering": "-price", "is_free": "false"},
])
def test_list_needs_at_most_4_queries(api, many_games, django_assert_max_num_queries, params):
    with django_assert_max_num_queries(4):
        response = api.get("/api/games/", params)
    assert len(response.json()["results"]) == 20


def test_detail_needs_at_most_5_queries(api, many_games, django_assert_max_num_queries):
    with django_assert_max_num_queries(5):
        response = api.get("/api/games/7/")
    assert len(response.json()["tags"]) == 3


@pytest.mark.parametrize("url", ["/api/genres/", "/api/categories/", "/api/tags/"])
def test_lookups_need_2_queries(api, many_games, django_assert_num_queries, url):
    with django_assert_num_queries(2): 
        api.get(url)