# Game Catalog API

A REST API over Steam game metadata — genres, categories, tags with vote
counts, prices, release dates and review counts — with filtering, search,
"similar games" and a per-user wishlist.

Built with Django 5.2 LTS, Django REST Framework and PostgreSQL. The data comes
from the scraper in my [Steam game recommender](https://github.com/mdorociak/svgr).

## Stack

Python 3.14 · Django 5.2 · Django REST Framework · django-filter · PostgreSQL 16 ·
uv · Docker Compose · pytest · GitHub Actions

## Running it

### With Docker

```bash
docker compose up --build                     # API on http://localhost:8000, migrations run on start
docker compose run --rm web python manage.py import_games data/game_features.csv
docker compose run --rm web python manage.py createsuperuser   # for /admin/ and the wishlist
docker compose run --rm web pytest
```

### Locally with uv

```bash
uv sync
cp .env.example .env                          # Windows: copy .env.example .env
docker compose up -d db                       # only PostgreSQL in Docker
uv run python manage.py migrate
uv run python manage.py import_games data/game_features.csv
uv run python manage.py runserver
uv run pytest
```

Without `POSTGRES_DB` in the environment the app falls back to SQLite, so the
tests also run on a machine without Docker.

### Data

`game_features.csv` is produced by
[`build_features.py`](https://github.com/mdorociak/svgr/tree/main/ML%2BData) in
the recommender repository (run it with `--out game_features.csv`; the default
name is `game_features_v2.csv`). Put it in `data/` (the folder is git-ignored
for CSV files).

## API

All game endpoints are read-only. The browsable API at
http://localhost:8000/api/ lets you click through them.

| Endpoint | Description |
| --- | --- |
| `GET /api/games/` | Paginated list (20 per page) with filters, search and ordering |
| `GET /api/games/<appid>/` | Detail: categories and tags with vote counts, most votes first |
| `GET /api/games/<appid>/similar/` | Games sharing the most tags, ties broken by positive reviews; `?limit=` 1–50, default 10 |
| `GET /api/genres/`, `/api/categories/`, `/api/tags/` | Paginated, with `game_count`, most games first |
| `GET`, `POST /api/wishlist/` | The logged-in user's wishlist; `POST {"game": <appid>}` |
| `DELETE /api/wishlist/<id>/` | Remove an item from your own wishlist |

Game list parameters:

| Parameter | Example | Meaning |
| --- | --- | --- |
| `genre`, `category`, `tag` | `?genre=indie&tag=roguelike` | Case-insensitive name match |
| `min_price`, `max_price` | `?max_price=20` | Inclusive price range |
| `is_free` | `?is_free=true` | Price exactly 0; `false` = priced. An unknown price matches neither |
| `released_after`, `released_before` | `?released_after=2020-01-01` | Inclusive, `YYYY-MM-DD` |
| `search` | `?search=hollow` | Part of the name |
| `ordering` | `?ordering=-positive` | `name`, `release_date`, `price`, `positive`; prefix `-` for descending |

Example — games similar to Hades. The response is a plain list; one item
shown, values depend on the imported data:

```bash
curl "http://localhost:8000/api/games/1145360/similar/?limit=3"
```

```json
[
  {
    "appid": 2379780,
    "name": "Balatro",
    "release_date": "2024-02-20",
    "price": "14.99",
    "is_free": false,
    "positive": 150000,
    "negative": 3000,
    "genres": ["Casual", "Indie", "Strategy"],
    "shared_tags": 2
  }
]
```

## Design notes

**Tag votes live on the link.** Steam tags come with vote counts, so `Game.tags`
goes through a `GameTag` model that stores `votes`. Genres and categories have
no extra data and use plain many-to-many tables.

**The import is idempotent and batched.** `import_games` can run any number of
times: games are upserted with `bulk_create(update_conflicts=True)`, and each
batch's genre, category and tag links are replaced, so a tag removed from the
file disappears from the game. Everything runs in one transaction — a failed
import leaves the database as it was.

**What the import skips, and why.** An exploratory analysis of the same data
(in the recommender repo) found soundtracks, DLC and software among the "games",
so only rows typed `game` are imported. An empty price is stored as unknown
(`null`), not as free.

**Filters never duplicate rows.** Filtering through a many-to-many with a JOIN
can return a game once per matching row. The genre, category and tag filters
use `EXISTS` subqueries instead, so any combination of them returns each game
once.

**Stable pagination.** Ordering by a non-unique field (`price`, `name`) gets
`pk` appended as a tie-breaker, so no game is skipped or repeated across pages.

**No N+1 queries.** Each action prefetches only what its serializer needs, and
tests fix the query budget: the game list runs in at most 4 queries, the detail
in at most 5, a lookup list in 2 — whatever the number of games.

**Similar games in one query.** Games are filtered to those sharing a tag with
the target, then annotated with `Count("tags")`. Because the filter comes before
the annotation, the count covers only the shared tags.

**Wishlist safety.** The user is taken from the request, never from the body.
Another user's item returns 404 rather than 403, so the API does not reveal
which items exist. A duplicate is rejected with 400 by the serializer, and a
duplicate that slips past it in a race between two requests is caught at the
database's unique constraint and also returned as 400, not 500.

**Indexes.** Foreign keys already covered by the leading column of a unique
constraint (`GameTag.game`, `WishlistItem.user`) have no separate index.

## Tests and CI

250 tests with pytest and pytest-django cover the parsers, the import, every
endpoint and filter, permissions, query counts and the admin.

GitHub Actions runs them on every pull request against PostgreSQL 16, and
first checks that the tests really use PostgreSQL rather than silently falling
back to SQLite.

## Import performance

| Version | Time for the full file |
| --- | --- |
| One `update_or_create` per game | TODO |
| Batched `bulk_create` in one transaction | TODO |

## Project layout

```
catalog/
  models.py          Game, Genre, Category, Tag, GameTag, WishlistItem
  importing.py       Parsers for single CSV cells
  management/commands/import_games.py
  filters.py         Game filters and stable ordering
  serializers.py
  views.py
  admin.py
config/              Django settings and URLs
tests/
```
