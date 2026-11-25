import pytest
from rest_framework.authtoken.models import Token

from catalog.models import WishlistItem
from tests.factories import make_game

pytestmark = pytest.mark.django_db

URL = "/api/wishlist/"


@pytest.fixture
def games():
    make_game(10, "Counter-Strike")


@pytest.fixture
def agent(django_user_model):
    return django_user_model.objects.create_user(username="agent")


@pytest.fixture
def token(agent):
    return Token.objects.create(user=agent)


def test_valid_token_adds_the_game_for_the_tokens_owner(api, games, agent, token):
    api.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

    response = api.post(URL, {"game": 10}, format="json")

    assert response.status_code == 201
    assert WishlistItem.objects.get().user == agent


def test_missing_token_is_401(api, games, token):
    response = api.post(URL, {"game": 10}, format="json")

    assert response.status_code == 401
    assert not WishlistItem.objects.exists()


def test_wrong_token_is_401(api, games, token):
    api.credentials(HTTP_AUTHORIZATION="Token " + "0" * 40)

    response = api.post(URL, {"game": 10}, format="json")

    assert response.status_code == 401
    assert not WishlistItem.objects.exists()