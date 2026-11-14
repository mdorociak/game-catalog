import csv
import time
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalog.importing import (
    parse_int,
    parse_list,
    parse_price,
    parse_release_date,
    parse_tags,
)
from catalog.models import Category, Game, GameTag, Genre, Tag

REQUIRED_COLUMNS = (
    "appid", "name", "release_date", "price", "positive", "negative",
    "required_age", "genres", "categories", "tags",
)
GAME_FIELDS = ("name", "release_date", "price", "positive", "negative", "required_age")
NAME_MAX_LENGTH = Game._meta.get_field("name").max_length

GenreLink = Game.genres.through
CategoryLink = Game.categories.through


class Command(BaseCommand):
    help = "Import games from a Steam CSV. Safe to run repeatedly: it updates, never duplicates."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", type=Path, help="Path to the CSV file.")
        parser.add_argument(
            "--batch-size", type=int, default=1000,
            help="Games written per round of bulk queries (default 1000).",
        )

    def handle(self, *args, csv_path, batch_size, **options):
        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1.")
        started = time.perf_counter()

        games, non_games, invalid = self.read_games(csv_path)
        self.import_batched(games, batch_size)

        elapsed = time.perf_counter() - started
        summary = f"Imported {len(games)} games, skipped {non_games} non-games"
        if invalid:
            summary += f", skipped {invalid} rows without an appid or name"
        self.stdout.write(f"{summary} in {elapsed:.1f}s.")

    # -- reading ------------------------------------------------------------

    def read_games(self, path):
        games, non_games, invalid = {}, 0, 0
        try:
            with open(path, newline="", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                headers = reader.fieldnames or []
                missing = [c for c in REQUIRED_COLUMNS if c not in headers]
                if missing:
                    raise CommandError(
                        f"{path} is missing columns: {', '.join(missing)}. "
                        f"Found: {', '.join(headers) or 'none'}."
                    )
                has_type = "type" in headers

                for row in reader:
                    if has_type and (row["type"] or "").strip().lower() != "game":
                        non_games += 1
                        continue
                    record = self.parse_row(row)
                    if record is None:
                        invalid += 1
                        continue
                    games[record["appid"]] = record
        except OSError as e: 
            raise CommandError(f"Cannot read {path}: {e.strerror or e}") from e
        except (UnicodeDecodeError, csv.Error) as e:
            raise CommandError(f"{path} is not a valid UTF-8 CSV file: {e}") from e
        return games, non_games, invalid

    @staticmethod
    def parse_row(row):
        """One CSV row -> a clean dict, or None if it can't become a Game."""
        appid = parse_int(row["appid"], default=None)
        name = (row["name"] or "").strip()[:NAME_MAX_LENGTH]
        if not appid or not name:
            return None
        return {
            "appid": appid,
            "name": name,
            "release_date": parse_release_date(row["release_date"]),
            "price": parse_price(row["price"]),
            "positive": parse_int(row["positive"]),
            "negative": parse_int(row["negative"]),
            "required_age": parse_int(row["required_age"]),
            "genres": parse_list(row["genres"]),
            "categories": parse_list(row["categories"]),
            "tags": parse_tags(row["tags"]),
        }

    # -- writing ------------------------------------------------------------

    @transaction.atomic
    def import_batched(self, games, batch_size):
        records = list(games.values())
        genre_ids = self.ensure_names(Genre, (n for r in records for n in r["genres"]), batch_size)
        category_ids = self.ensure_names(Category, (n for r in records for n in r["categories"]), batch_size)
        tag_ids = self.ensure_names(Tag, (n for r in records for n in r["tags"]), batch_size)

        for start in range(0, len(records), batch_size):
            batch = records[start:start + batch_size]
            appids = [r["appid"] for r in batch]

            Game.objects.bulk_create(
                [Game(appid=r["appid"], **{f: r[f] for f in GAME_FIELDS}) for r in batch],
                update_conflicts=True,
                unique_fields=["appid"],
                update_fields=list(GAME_FIELDS),
            )

            GenreLink.objects.filter(game_id__in=appids).delete()
            GenreLink.objects.bulk_create(
                [GenreLink(game_id=r["appid"], genre_id=genre_ids[n]) for r in batch for n in r["genres"]],
                batch_size=batch_size,
            )
            CategoryLink.objects.filter(game_id__in=appids).delete()
            CategoryLink.objects.bulk_create(
                [CategoryLink(game_id=r["appid"], category_id=category_ids[n]) for r in batch for n in r["categories"]],
                batch_size=batch_size,
            )
            GameTag.objects.filter(game_id__in=appids).delete()
            GameTag.objects.bulk_create(
                [
                    GameTag(game_id=r["appid"], tag_id=tag_ids[name], votes=votes)
                    for r in batch
                    for name, votes in r["tags"].items()
                ],
                batch_size=batch_size,
            )

    @staticmethod
    def ensure_names(model, names, batch_size):
        names = set(names)
        model.objects.bulk_create(
            [model(name=n) for n in names], ignore_conflicts=True, batch_size=batch_size
        )
        return dict(model.objects.filter(name__in=names).values_list("name", "id"))