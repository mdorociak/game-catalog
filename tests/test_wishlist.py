from datetime import datetime, timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from catalog.models import WishlistItem
from catalog.serializers import WishlistItemSerializer
from tests.factories import make_game

pytestmark = pytest.mark.django_db

URL = "/api/wishlist/"


@pytest.fixture
def games():
    make_game(1145360, "Hades")
    make_game(10, "Counter-Strike")
    make_game(70, "Half-Life")


@pytest.fixture
def alice(django_user_model):
    return django_user_model.objects.create_user(username="alice", password="x")


@pytest.fixture
def bob(django_user_model):
    return django_user_model.objects.create_user(username="bob", password="x")


@pytest.fixture
def anon():
    return APIClient()


@pytest.fixture
def api(alice):
    client = APIClient()
    client.force_login(alice)
    return client


def add(user, appid, minutes_ago=0):
    item = WishlistItem.objects.create(user=user, game_id=appid)
    if minutes_ago:
        WishlistItem.objects.filter(pk=item.pk).update(
            added_at=timezone.now() - timedelta(minutes=minutes_ago)
        )
    return item


# -- login required --------------------------------------------------------

@pytest.mark.parametrize("method, url", [
    ("get", URL), ("post", URL), ("delete", f"{URL}1/"),
])
def test_anonymous_requests_are_refused(anon, games, alice, method, url):
    add(alice, 10)
    response = getattr(anon, method)(url, {"game": 70}, format="json")
    assert response.status_code in (401, 403)
    assert WishlistItem.objects.count() == 1  


# -- list ----------------------------------------------------------------

def test_list_shape(api, games, alice):
    item = add(alice, 1145360)
    [entry] = api.get(URL).json()
    assert entry == {
        "id": item.id,
        "game": 1145360,
        "game_name": "Hades",
        "added_at": entry["added_at"],  
    }
    assert datetime.fromisoformat(entry["added_at"]) == item.added_at 


def test_list_newest_first(api, games, alice):
    add(alice, 10, minutes_ago=30)
    add(alice, 1145360, minutes_ago=1)
    add(alice, 70, minutes_ago=10)
    assert [i["game_name"] for i in api.get(URL).json()] == ["Hades", "Half-Life", "Counter-Strike"]


def test_users_only_see_their_own_items(games, alice, bob):
    add(alice, 10)
    add(bob, 70)
    add(bob, 1145360)
    for user, expected in ((alice, ["Counter-Strike"]), (bob, ["Hades", "Half-Life"])):
        client = APIClient()
        client.force_login(user)
        assert sorted(i["game_name"] for i in client.get(URL).json()) == expected


def test_empty_wishlist_is_an_empty_list(api, games):
    response = api.get(URL)
    assert response.status_code == 200
    assert response.json() == []


def test_list_needs_at_most_3_queries(api, alice, django_assert_max_num_queries):
    for appid in range(1, 31):
        make_game(appid, f"Game {appid}")
        add(alice, appid)

    with django_assert_max_num_queries(3): 
        response = api.get(URL)
    assert len(response.json()) == 30


# -- add ------------------------------------------------------------------

def test_add_a_game(api, games, alice):
    response = api.post(URL, {"game": 1145360}, format="json")

    assert response.status_code == 201
    body = response.json()
    assert (body["game"], body["game_name"]) == (1145360, "Hades")
    assert set(body) == {"id", "game", "game_name", "added_at"}
    assert WishlistItem.objects.get(pk=body["id"]).user == alice


def test_user_in_the_request_is_ignored(api, games, alice, bob):
    response = api.post(URL, {"game": 10, "user": bob.id}, format="json")

    assert response.status_code == 201
    assert WishlistItem.objects.get().user == alice
    assert not bob.wishlist_items.exists()


def test_adding_the_same_game_twice_is_400_not_500(api, games, alice):
    api.post(URL, {"game": 10}, format="json")
    response = api.post(URL, {"game": 10}, format="json")

    assert response.status_code == 400
    assert response.json() == {"non_field_errors": ["This game is already on your wishlist."]}
    assert alice.wishlist_items.count() == 1


def test_two_users_can_add_the_same_game(games, alice, bob):
    for user in (alice, bob):
        client = APIClient()
        client.force_login(user)
        assert client.post(URL, {"game": 10}, format="json").status_code == 201


def test_game_can_be_added_again_after_removing_it(api, games, alice):
    item = add(alice, 10)
    api.delete(f"{URL}{item.id}/")
    assert api.post(URL, {"game": 10}, format="json").status_code == 201


@pytest.mark.parametrize("body", [{"game": 999999}, {"game": "abc"}, {}, {"game": None}])
def test_unknown_or_missing_game_is_400(api, games, body):
    response = api.post(URL, body, format="json")
    assert response.status_code == 400
    assert "game" in response.json()
    assert not WishlistItem.objects.exists()


def test_simultaneous_duplicate_is_400_not_500(api, games, alice, monkeypatch):
    def sneak_in_a_duplicate(self, attrs):
        WishlistItem.objects.create(user=alice, game_id=10)
        return attrs

    monkeypatch.setattr(WishlistItemSerializer, "validate", sneak_in_a_duplicate)
    response = api.post(URL, {"game": 10}, format="json")

    assert response.status_code == 400
    assert response.json() == {"non_field_errors": ["This game is already on your wishlist."]}
    assert alice.wishlist_items.count() == 1


# -- remove --------------------------------------------------------------

def test_remove_own_item(api, games, alice):
    item = add(alice, 10)
    keep = add(alice, 70)

    response = api.delete(f"{URL}{item.id}/")

    assert response.status_code == 204
    assert list(alice.wishlist_items.all()) == [keep]


def test_someone_elses_item_is_404_and_stays(api, games, bob):
    item = add(bob, 10)
    response = api.delete(f"{URL}{item.id}/")
    assert response.status_code == 404
    assert WishlistItem.objects.filter(pk=item.pk).exists()


def test_unknown_item_is_404(api, games):
    assert api.delete(f"{URL}12345/").status_code == 404


# -- not allowed -------------------------------------------------------

@pytest.mark.parametrize("method", ["put", "patch"])
def test_updates_are_not_allowed(api, games, alice, method):
    item = add(alice, 10)
    response = getattr(api, method)(f"{URL}{item.id}/", {"game": 70}, format="json")
    assert response.status_code == 405
    assert WishlistItem.objects.get(pk=item.pk).game_id == 10