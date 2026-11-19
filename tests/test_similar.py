import pytest

from tests.factories import make_game

pytestmark = pytest.mark.django_db

HADES = "/api/games/1145360/similar/"


@pytest.fixture
def games():
    make_game(1145360, "Hades", positive=250000, genres=["Action", "Indie", "RPG"],
              tags={"Roguelike": 500, "Action": 400, "Indie": 300, "Mythology": 100})
    make_game(2379780, "Balatro", positive=150000, genres=["Strategy", "Indie"],
              tags={"Roguelike": 900, "Indie": 800, "Card Game": 700, "Deckbuilding": 600, "Poker": 50})
    make_game(367520, "Hollow Knight", positive=300000, genres=["Action", "Indie"],
              tags={"Metroidvania": 900, "Indie": 500, "Souls-like": 400})
    make_game(10, "Counter-Strike", positive=124534, genres=["Action"],
              tags={"FPS": 800, "Action": 900})
    make_game(1361210, "Warhammer 40,000: Darktide", positive=80000, genres=["Action"],
              tags={"Action": 300, "Co-op": 200})
    make_game(70, "Half-Life", positive=27755, genres=["Action"],
              tags={"FPS": 600, "Action": 500, "Classic": 400})
    make_game(413150, "Stardew Valley", positive=500000, genres=["Simulation"],
              tags={"Farming Sim": 900, "Pixel Graphics": 800})  
    make_game(400, "No Tags", positive=999999, genres=["Action"])


def ranking(response):
    assert response.status_code == 200, response.content
    return [(g["name"], g["shared_tags"]) for g in response.json()]


def test_spec_example(api, games):
    assert ranking(api.get(HADES)) == [
        ("Balatro", 2),                
        ("Hollow Knight", 1),              
        ("Counter-Strike", 1),              
        ("Warhammer 40,000: Darktide", 1),  
        ("Half-Life", 1),                   
    ]


def test_item_has_list_fields_plus_shared_tags(api, games):
    balatro = api.get(HADES).json()[0]
    assert balatro == {
        "appid": 2379780,
        "name": "Balatro",
        "release_date": "2020-01-01",
        "price": "9.99",
        "is_free": False,
        "positive": 150000,
        "negative": 10,
        "genres": ["Indie", "Strategy"],
        "shared_tags": 2,  
    }


def test_excludes_the_game_itself_and_games_with_nothing_in_common(api, games):
    names = [name for name, _ in ranking(api.get(HADES))]
    assert "Hades" not in names
    assert "Stardew Valley" not in names
    assert "No Tags" not in names


def test_response_is_a_plain_list_without_pagination(api, games):
    assert isinstance(api.get(HADES).json(), list)


def test_ties_on_shared_tags_and_positive_go_by_appid(api):
    make_game(1, "Base", tags={"FPS": 1})
    for appid in (30, 20, 40):
        make_game(appid, f"Twin {appid}", positive=5, tags={"FPS": 1})
    assert [g["appid"] for g in api.get("/api/games/1/similar/").json()] == [20, 30, 40]


# -- limit --------------------------------------------------------------------

def test_limit(api, games):
    assert ranking(api.get(HADES, {"limit": 2})) == [("Balatro", 2), ("Hollow Knight", 1)]


@pytest.fixture
def sixty_neighbours():
    make_game(1, "Base", tags={"Shared": 1})
    for appid in range(2, 62):
        make_game(appid, f"Game {appid}", tags={"Shared": 1})


@pytest.mark.parametrize("params, expected_length", [
    ({}, 10),                
    ({"limit": 50}, 50),
    ({"limit": 51}, 50),       
    ({"limit": 1000}, 50),
    ({"limit": 1}, 1),
])
def test_limit_default_and_cap(api, sixty_neighbours, params, expected_length):
    response = api.get("/api/games/1/similar/", params)
    assert response.status_code == 200
    assert len(response.json()) == expected_length


@pytest.mark.parametrize("limit", ["abc", "0", "-1", "1.5", ""])
def test_invalid_limit_is_400(api, games, limit):
    response = api.get(HADES, {"limit": limit})
    assert response.status_code == 400
    assert "limit" in response.json()


# -- edge cases ---------------------------------------------------------------

def test_unknown_game_is_404(api, games):
    assert api.get("/api/games/999999/similar/").status_code == 404


def test_game_without_tags_gets_empty_list(api, games):
    response = api.get("/api/games/400/similar/")
    assert response.status_code == 200
    assert response.json() == []


def test_only_get_is_allowed(api, games):
    assert api.post(HADES).status_code == 405


def test_needs_at_most_3_queries(api, django_assert_max_num_queries):
    make_game(1, "Base", genres=["Action"], tags={"A": 1, "B": 1, "C": 1})
    for appid in range(2, 40):
        make_game(appid, f"Game {appid}", genres=["Action", f"G{appid % 4}"],
                  tags={"A": 1, "B": 1, f"T{appid}": 1})

    with django_assert_max_num_queries(3): 
        response = api.get("/api/games/1/similar/", {"limit": 50})
    assert len(response.json()) == 38