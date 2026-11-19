from datetime import date
from decimal import Decimal

from catalog.models import Category, Game, GameTag, Genre, Tag


def make_game(appid, name, *, price="9.99", release_date=date(2020, 1, 1),
              positive=100, negative=10, required_age=0,
              genres=(), categories=(), tags=None):
    game = Game.objects.create(
        appid=appid, name=name,
        price=None if price is None else Decimal(price),
        release_date=release_date, positive=positive, negative=negative,
        required_age=required_age,
    )
    game.genres.set([Genre.objects.get_or_create(name=n)[0] for n in genres])
    game.categories.set([Category.objects.get_or_create(name=n)[0] for n in categories])
    for tag_name, votes in (tags or {}).items():
        GameTag.objects.create(
            game=game, tag=Tag.objects.get_or_create(name=tag_name)[0], votes=votes
        )
    return game
