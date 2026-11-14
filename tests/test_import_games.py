import csv
import re
from datetime import date
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from catalog.models import Category, Game, GameTag, Genre, Tag, WishlistItem

COLUMNS = [
    "appid", "name", "type", "release_date", "price", "positive", "negative",
    "required_age", "genres", "categories", "tags",
]


def row(appid, name, *, type="game", release_date="1 Jan, 2020", price="9.99",
        positive="100", negative="10", required_age="0",
        genres="['Action']", categories="['Single-player']", tags="{'Action': 10}"):
    return {
        "appid": appid, "name": name, "type": type, "release_date": release_date,
        "price": price, "positive": positive, "negative": negative,
        "required_age": required_age, "genres": genres, "categories": categories,
        "tags": tags,
    }


SAMPLE = [
    row("1145360", "Hades", release_date="17 Sep, 2020", price="24.5",
        positive="250000", negative="4000",
        genres="['Action', 'Indie', 'RPG']",
        tags="{'Roguelike': 500, 'Action': 400, 'Indie': 300}"),
    row("1361210", "Warhammer 40,000: Darktide", release_date="Nov 30, 2022",
        price="39.99", required_age="18.0", categories="['Multi-player', 'Online PvP']"),
    row("10", "Counter-Strike", price="0.0", positive="124534.0",
        genres="['Action']", tags="{'FPS': 900, 'Action': 200}"),
    row("400", "Mystery Game", release_date="Coming soon", price=""),
    row("500", "Tagless", tags="{}", genres="[]", categories=""),
    row("900", "Hades Original Soundtrack", type="music"),
    row("901", "Some DLC", type="dlc"),
]

def write_csv(path, rows, columns=COLUMNS):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def run_import(path, **options):
    out = StringIO()
    call_command("import_games", str(path), stdout=out, **options)
    return out.getvalue()


def snapshot():
    return {
        "games": list(Game.objects.order_by("appid").values()),
        "genres": sorted(Game.genres.through.objects.values_list("game_id", "genre__name")),
        "categories": sorted(Game.categories.through.objects.values_list("game_id", "category__name")),
        "tags": sorted(GameTag.objects.values_list("game_id", "tag__name", "votes")),
        "names": (
            sorted(Genre.objects.values_list("name", flat=True)),
            sorted(Category.objects.values_list("name", flat=True)),
            sorted(Tag.objects.values_list("name", flat=True)),
        ),
    }


@pytest.fixture
def sample_csv(tmp_path):
    return write_csv(tmp_path / "games.csv", SAMPLE)


pytestmark = pytest.mark.django_db


# -- what gets imported ---------------------------------------------------------

def test_imports_games_and_skips_non_games(sample_csv):
    output = run_import(sample_csv)

    assert Game.objects.count() == 5
    assert not Game.objects.filter(appid__in=[900, 901]).exists()
    assert re.fullmatch(r"Imported 5 games, skipped 2 non-games in \d+\.\ds\.\n", output)


def test_field_values(sample_csv):
    run_import(sample_csv)

    hades = Game.objects.get(appid=1145360)
    assert hades.name == "Hades"
    assert hades.release_date == date(2020, 9, 17)
    assert hades.price == Decimal("24.50")
    assert (hades.positive, hades.negative) == (250000, 4000)
    assert [g.name for g in hades.genres.all()] == ["Action", "Indie", "RPG"]
    assert [(gt.tag.name, gt.votes) for gt in hades.game_tags.all()] == [
        ("Roguelike", 500), ("Action", 400), ("Indie", 300),
    ]

    darktide = Game.objects.get(appid=1361210)
    assert darktide.name == "Warhammer 40,000: Darktide"
    assert darktide.release_date == date(2022, 11, 30)
    assert darktide.required_age == 18

    cs = Game.objects.get(appid=10)
    assert cs.price == Decimal("0") and cs.is_free
    assert cs.positive == 124534

    mystery = Game.objects.get(appid=400)
    assert mystery.release_date is None
    assert mystery.price is None and not mystery.is_free

    tagless = Game.objects.get(appid=500)
    assert not tagless.game_tags.exists()
    assert not tagless.genres.exists() and not tagless.categories.exists()


def test_one_row_per_name_shared_by_all_games(sample_csv):
    run_import(sample_csv)

    action = Genre.objects.get(name="Action")
    assert action.games.count() == 4
    assert Tag.objects.filter(name="Action").count() == 1
    assert Tag.objects.get(name="Action").games.count() == 4


# -- idempotency and updates --------------------------------------------------

def test_second_run_changes_nothing(sample_csv):
    run_import(sample_csv)
    before = snapshot()
    run_import(sample_csv)
    assert snapshot() == before


def test_batch_size_does_not_change_the_result(sample_csv):
    run_import(sample_csv)
    one_batch = snapshot()
    GameTag.objects.all().delete()
    Game.objects.all().delete()
    Tag.objects.all().delete()
    Genre.objects.all().delete()
    Category.objects.all().delete()

    run_import(sample_csv, batch_size=1)
    assert snapshot() == one_batch


def test_changed_file_updates_games_and_their_links(tmp_path):
    run_import(write_csv(tmp_path / "v1.csv", SAMPLE))

    changed = [dict(r) for r in SAMPLE]
    changed[0].update(
        name="Hades (2020)", price="19.99",
        genres="['Action', 'Roguelike']",
        tags="{'Roguelike': 600, 'Mythology': 50}",
    )
    run_import(write_csv(tmp_path / "v2.csv", changed))

    hades = Game.objects.get(appid=1145360)
    assert hades.name == "Hades (2020)"
    assert hades.price == Decimal("19.99")
    assert [g.name for g in hades.genres.all()] == ["Action", "Roguelike"]
    assert [(gt.tag.name, gt.votes) for gt in hades.game_tags.all()] == [
        ("Roguelike", 600), ("Mythology", 50),
    ]
    assert Tag.objects.filter(name="Indie").exists()
    assert not Tag.objects.get(name="Indie").games.exists()
    assert Tag.objects.get(name="Action").games.count() == 3
    assert Game.objects.count() == 5


def test_games_missing_from_the_file_are_kept(tmp_path):
    run_import(write_csv(tmp_path / "v1.csv", SAMPLE))
    run_import(write_csv(tmp_path / "v2.csv", SAMPLE[:1]))
    assert Game.objects.count() == 5


def test_reimport_keeps_wishlists(sample_csv):
    run_import(sample_csv)
    user = get_user_model().objects.create_user(username="alice", password="x")
    WishlistItem.objects.create(user=user, game_id=1145360)

    run_import(sample_csv)

    assert user.wishlist_items.get().game.name == "Hades"


# -- odd input ----------------------------------------------------------------

def test_without_type_column_every_row_is_imported(tmp_path):
    columns = [c for c in COLUMNS if c != "type"]
    output = run_import(write_csv(tmp_path / "old.csv", SAMPLE, columns))
    assert Game.objects.count() == 7
    assert "skipped 0 non-games" in output


def test_extra_columns_are_ignored(tmp_path):
    rows = [dict(r, has_features="1") for r in SAMPLE]
    run_import(write_csv(tmp_path / "v2.csv", rows, COLUMNS + ["has_features"]))
    assert Game.objects.count() == 5


def test_duplicate_appid_last_row_wins(tmp_path):
    rows = [row("1", "First"), row("1", "Second", tags="{'Puzzle': 5}")]
    output = run_import(write_csv(tmp_path / "dup.csv", rows))

    assert output.startswith("Imported 1 games")
    game = Game.objects.get(appid=1)
    assert game.name == "Second"
    assert [gt.tag.name for gt in game.game_tags.all()] == ["Puzzle"]


def test_bad_cells_do_not_stop_the_import(tmp_path):
    rows = [
        row("1", "Broken cells", release_date="Q3 2025", price="free",
            positive="lots", genres="not a list", categories="{'a': 1}",
            tags="{broken"),
        row("2", "Fine"),
    ]
    run_import(write_csv(tmp_path / "bad.csv", rows))

    broken = Game.objects.get(appid=1)
    assert broken.release_date is None and broken.price is None
    assert broken.positive == 0
    assert not broken.genres.exists() and not broken.game_tags.exists()
    assert Game.objects.filter(appid=2).exists()


def test_rows_without_appid_or_name_are_skipped_and_reported(tmp_path):
    rows = [row("", "No id"), row("abc", "Bad id"), row("3", "  "), row("4", "Good")]
    output = run_import(write_csv(tmp_path / "invalid.csv", rows))

    assert list(Game.objects.values_list("appid", flat=True)) == [4]
    assert "skipped 3 rows without an appid or name" in output


def test_empty_file_with_header_imports_nothing(tmp_path):
    output = run_import(write_csv(tmp_path / "empty.csv", []))
    assert output.startswith("Imported 0 games, skipped 0 non-games")


def test_batched_import_is_all_or_nothing(sample_csv, monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError("database went away")

    monkeypatch.setattr(GameTag.objects, "bulk_create", explode)
    with pytest.raises(RuntimeError):
        run_import(sample_csv)

    assert Game.objects.count() == 0
    assert Genre.objects.count() == 0


# -- errors -------------------------------------------------------------------

def test_missing_file_is_a_command_error(tmp_path):
    with pytest.raises(CommandError, match="Cannot read"):
        run_import(tmp_path / "nope.csv")


def test_directory_is_a_command_error(tmp_path):
    with pytest.raises(CommandError):
        run_import(tmp_path)


def test_missing_columns_are_named(tmp_path):
    path = write_csv(tmp_path / "wrong.csv", [], columns=["AppID", "Name", "tags"])
    with pytest.raises(CommandError, match="missing columns: appid, name, release_date"):
        run_import(path)


def test_batch_size_must_be_positive(sample_csv):
    with pytest.raises(CommandError, match="batch-size"):
        run_import(sample_csv, batch_size=0)


# -- performance --------------------------------------------------------------

def count_queries(path):
    with CaptureQueriesContext(connection) as ctx:
        run_import(path)
    return len(ctx)


def test_batched_query_count_does_not_grow_with_rows(tmp_path):
    def rows(n):
        return [row(str(i), f"Game {i}", tags=f"{{'T{i % 7}': {i}, 'Common': 1}}") for i in range(1, n + 1)]

    small = count_queries(write_csv(tmp_path / "small.csv", rows(5)))
    GameTag.objects.all().delete()
    Game.objects.all().delete()
    large = count_queries(write_csv(tmp_path / "large.csv", rows(100)))

    assert large == small