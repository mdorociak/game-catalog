import pytest
from django.contrib import admin

from catalog.models import Category, Game, Genre, Tag, WishlistItem
from tests.factories import make_game

pytestmark = pytest.mark.django_db

CHANGELIST = "/admin/catalog/game/"


@pytest.fixture
def games():
    make_game(1145360, "Hades", positive=250000, genres=["Action", "Indie"],
              categories=["Single-player"], tags={"Roguelike": 500, "Action": 400})
    make_game(367520, "Hollow Knight", positive=300000, genres=["Indie"],
              tags={"Metroidvania": 900})
    make_game(10, "Counter-Strike", positive=124534, genres=["Action"],
              tags={"FPS": 800})


def listed_appids(response):
    assert response.status_code == 200
    return sorted(game.appid for game in response.context["cl"].result_list)


@pytest.mark.parametrize("model", [Game, Genre, Category, Tag, WishlistItem])
def test_models_are_registered(model):
    assert admin.site.is_registered(model)


def test_changelist_columns(admin_client, games):
    response = admin_client.get(CHANGELIST)
    assert list(response.context["cl"].list_display) == [
        "action_checkbox", "appid", "name", "release_date", "price", "positive",
    ]


def test_search_by_name(admin_client, games):
    assert listed_appids(admin_client.get(CHANGELIST, {"q": "hades"})) == [1145360]


def test_filter_by_genre(admin_client, games):
    action = Genre.objects.get(name="Action")
    response = admin_client.get(CHANGELIST, {"genres__id__exact": action.pk})
    assert listed_appids(response) == [10, 1145360]


def test_genre_filter_is_in_the_sidebar(admin_client, games):
    content = admin_client.get(CHANGELIST).content.decode()
    assert 'id="changelist-filter"' in content
    assert "Indie" in content


def test_edit_page_shows_tags_inline_without_loading_every_tag(admin_client, games):
    Tag.objects.create(name="Unrelated Tag")  

    response = admin_client.get("/admin/catalog/game/1145360/change/")
    content = response.content.decode()

    assert response.status_code == 200
    assert 'name="game_tags-0-votes"' in content       
    assert "admin-autocomplete" in content             
    assert "Unrelated Tag" not in content              


def test_edit_page_does_not_query_twice_per_tag_row(admin_client, django_assert_max_num_queries):
    make_game(1, "Many tags", tags={f"Tag {i}": i for i in range(20)})
    with django_assert_max_num_queries(35):
        admin_client.get("/admin/catalog/game/1/change/")


def test_tag_autocomplete_searches_by_name(admin_client, games):
    response = admin_client.get("/admin/autocomplete/", {
        "app_label": "catalog", "model_name": "gametag",
        "field_name": "tag", "term": "rogue",
    })
    assert [r["text"] for r in response.json()["results"]] == ["Roguelike"]


def test_change_a_games_tags(admin_client, games):
    hades = Game.objects.get(appid=1145360)
    roguelike, action = (hades.game_tags.get(tag__name=n) for n in ("Roguelike", "Action"))
    mythology = Tag.objects.create(name="Mythology")

    data = {
        "appid": 1145360, "name": "Hades", "release_date": "2020-01-01",
        "price": "9.99", "positive": 250000, "negative": 10, "required_age": 0,
        "genres": [g.pk for g in hades.genres.all()],
        "categories": [c.pk for c in hades.categories.all()],
        "game_tags-TOTAL_FORMS": 3, "game_tags-INITIAL_FORMS": 2,
        "game_tags-MIN_NUM_FORMS": 0, "game_tags-MAX_NUM_FORMS": 1000,
        "game_tags-0-id": roguelike.pk, "game_tags-0-game": 1145360,
        "game_tags-0-tag": roguelike.tag_id, "game_tags-0-votes": 600,
        "game_tags-1-id": action.pk, "game_tags-1-game": 1145360,
        "game_tags-1-tag": action.tag_id, "game_tags-1-votes": 400,
        "game_tags-1-DELETE": "on",
        "game_tags-2-game": 1145360, "game_tags-2-tag": mythology.pk,
        "game_tags-2-votes": 50,
    }
    response = admin_client.post("/admin/catalog/game/1145360/change/", data)

    assert response.status_code == 302, response.context["errors"]
    assert [(gt.tag.name, gt.votes) for gt in hades.game_tags.all()] == [
        ("Roguelike", 600), ("Mythology", 50),
    ]


def test_adding_a_tag_the_game_already_has_is_a_form_error(admin_client, games):
    hades = Game.objects.get(appid=1145360)
    rows = list(hades.game_tags.all())
    data = {
        "appid": 1145360, "name": "Hades", "release_date": "2020-01-01",
        "price": "9.99", "positive": 250000, "negative": 10, "required_age": 0,
        "genres": [g.pk for g in hades.genres.all()],
        "game_tags-TOTAL_FORMS": 3, "game_tags-INITIAL_FORMS": 2,
        "game_tags-MIN_NUM_FORMS": 0, "game_tags-MAX_NUM_FORMS": 1000,
        "game_tags-2-game": 1145360, "game_tags-2-tag": rows[0].tag_id,
        "game_tags-2-votes": 1,
    }
    for i, gt in enumerate(rows):
        data |= {
            f"game_tags-{i}-id": gt.pk, f"game_tags-{i}-game": 1145360,
            f"game_tags-{i}-tag": gt.tag_id, f"game_tags-{i}-votes": gt.votes,
        }

    response = admin_client.post("/admin/catalog/game/1145360/change/", data)

    assert response.status_code == 200  
    assert "duplicate data for tag" in response.content.decode() 
    assert hades.game_tags.count() == 2


def test_wishlist_changelist(admin_client, games, django_user_model):
    user = django_user_model.objects.create_user(username="alice", password="x")
    WishlistItem.objects.create(user=user, game_id=10)
    response = admin_client.get("/admin/catalog/wishlistitem/")
    assert response.status_code == 200
    assert "Counter-Strike" in response.content.decode()