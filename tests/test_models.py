from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone

from catalog.models import Category, Game, GameTag, Genre, Tag, WishlistItem

User = get_user_model()


class NamedModelTests(TestCase):
    def test_str_returns_name(self):
        for model in (Genre, Category, Tag):
            with self.subTest(model=model.__name__):
                self.assertEqual(str(model.objects.create(name="Indie")), "Indie")

    def test_name_is_unique(self):
        for model in (Genre, Category, Tag):
            with self.subTest(model=model.__name__):
                model.objects.create(name="Indie")
                with self.assertRaises(IntegrityError), transaction.atomic():
                    model.objects.create(name="Indie")

    def test_game_genres_come_out_alphabetically(self):
        game = Game.objects.create(appid=1, name="G")
        for name in ("Strategy", "Action", "RPG"):
            game.genres.add(Genre.objects.create(name=name))
        self.assertEqual(
            [g.name for g in game.genres.all()], ["Action", "RPG", "Strategy"]
        )

    def test_categories_come_out_alphabetically(self):
        game = Game.objects.create(appid=1, name="G")
        for name in ("Steam Cloud", "Achievements", "Multi-player"):
            game.categories.add(Category.objects.create(name=name))
        expected = ["Achievements", "Multi-player", "Steam Cloud"]
 
        self.assertEqual([c.name for c in Category.objects.all()], expected)
        self.assertEqual([c.name for c in game.categories.all()], expected)


class GameTests(TestCase):
    def test_appid_is_the_primary_key(self):
        game = Game.objects.create(appid=730, name="Counter-Strike 2")
        self.assertEqual(game.pk, 730)
        self.assertEqual(Game._meta.pk.name, "appid")
        field_names = [f.name for f in Game._meta.get_fields()]
        self.assertNotIn("id", field_names)

    def test_defaults(self):
        game = Game.objects.create(appid=1, name="G")
        game.refresh_from_db()
        self.assertIsNone(game.price)
        self.assertIsNone(game.release_date)
        self.assertEqual(
            (game.positive, game.negative, game.required_age), (0, 0, 0)
        )

    def test_str_returns_name(self):
        self.assertEqual(str(Game(appid=1, name="Portal")), "Portal")

    def test_is_free(self):
        cases = [
            (Decimal("0"), True),
            (Decimal("0.00"), True),
            (Decimal("0.01"), False),
            (Decimal("9.99"), False),
            (None, False),
        ]
        for price, expected in cases:
            with self.subTest(price=price):
                self.assertIs(Game(appid=1, name="G", price=price).is_free, expected)

    def test_is_free_after_reload_from_db(self):
        Game.objects.create(appid=1, name="G", price=Decimal("0.00"))
        self.assertTrue(Game.objects.get(appid=1).is_free)

    def test_default_ordering_by_appid(self):
        for appid in (30, 10, 20):
            Game.objects.create(appid=appid, name=f"G{appid}")
        self.assertEqual(
            list(Game.objects.values_list("appid", flat=True)), [10, 20, 30]
        )

    def test_reverse_names(self):
        game = Game.objects.create(appid=1, name="G")
        genre = Genre.objects.create(name="Action")
        category = Category.objects.create(name="Single-player")
        tag = Tag.objects.create(name="FPS")
        game.genres.add(genre)
        game.categories.add(category)
        GameTag.objects.create(game=game, tag=tag, votes=3)

        self.assertEqual(list(genre.games.all()), [game])
        self.assertEqual(list(category.games.all()), [game])
        self.assertEqual(list(tag.games.all()), [game])
        self.assertEqual(list(game.tags.all()), [tag])
        self.assertEqual(game.game_tags.get().votes, 3)


class GameTagTests(TestCase):
    def setUp(self):
        self.game = Game.objects.create(appid=1, name="G")

    def test_votes_default_to_zero(self):
        gt = GameTag.objects.create(game=self.game, tag=Tag.objects.create(name="FPS"))
        self.assertEqual(gt.votes, 0)

    def test_a_game_carries_a_tag_only_once(self):
        tag = Tag.objects.create(name="FPS")
        GameTag.objects.create(game=self.game, tag=tag, votes=1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            GameTag.objects.create(game=self.game, tag=tag, votes=2)

    def test_same_tag_on_different_games_is_fine(self):
        tag = Tag.objects.create(name="FPS")
        other = Game.objects.create(appid=2, name="H")
        GameTag.objects.create(game=self.game, tag=tag)
        GameTag.objects.create(game=other, tag=tag)
        self.assertEqual(tag.games.count(), 2)

    def test_ordered_by_most_votes_first(self):
        for name, votes in (("A", 5), ("B", 50), ("C", 20)):
            GameTag.objects.create(
                game=self.game, tag=Tag.objects.create(name=name), votes=votes
            )
        self.assertEqual(
            [gt.tag.name for gt in self.game.game_tags.all()], ["B", "C", "A"]
        )


class WishlistItemTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="alice", password="x")
        self.game = Game.objects.create(appid=1, name="G")

    def test_added_at_is_set_on_creation(self):
        before = timezone.now()
        item = WishlistItem.objects.create(user=self.user, game=self.game)
        self.assertIsNotNone(item.added_at)
        self.assertGreaterEqual(item.added_at, before)

    def test_reverse_name_on_user(self):
        item = WishlistItem.objects.create(user=self.user, game=self.game)
        self.assertEqual(list(self.user.wishlist_items.all()), [item])

    def test_a_user_wishlists_a_game_only_once(self):
        WishlistItem.objects.create(user=self.user, game=self.game)
        with self.assertRaises(IntegrityError), transaction.atomic():
            WishlistItem.objects.create(user=self.user, game=self.game)

    def test_two_users_can_wishlist_the_same_game(self):
        bob = User.objects.create_user(username="bob", password="x")
        WishlistItem.objects.create(user=self.user, game=self.game)
        WishlistItem.objects.create(user=bob, game=self.game)
        self.assertEqual(WishlistItem.objects.filter(game=self.game).count(), 2)

    def test_ordered_newest_first(self):
        games = [Game.objects.create(appid=i, name=f"G{i}") for i in (2, 3, 4)]
        items = [WishlistItem.objects.create(user=self.user, game=g) for g in games]
        now = timezone.now()
        for item, age in zip(items, (timedelta(days=2), timedelta(0), timedelta(days=1))):
            WishlistItem.objects.filter(pk=item.pk).update(added_at=now - age)
        self.assertEqual(
            [i.game.appid for i in self.user.wishlist_items.all()], [3, 4, 2]
        )

    def test_same_instant_ties_broken_by_id(self):
        games = [Game.objects.create(appid=i, name=f"G{i}") for i in (2, 3, 4)]
        items = [WishlistItem.objects.create(user=self.user, game=g) for g in games]
        WishlistItem.objects.update(added_at=timezone.now())
        expected = sorted((i.pk for i in items), reverse=True)
        self.assertEqual(
            list(self.user.wishlist_items.values_list("pk", flat=True)), expected
        )


class OnDeleteTests(TestCase):

    def setUp(self):
        self.game = Game.objects.create(appid=1, name="G")
        self.action = Tag.objects.create(name="Action")
        GameTag.objects.create(game=self.game, tag=self.action, votes=10)

    def test_tag_in_use_cannot_be_deleted(self):
        with self.assertRaises(ProtectedError):
            self.action.delete()
        self.assertTrue(Tag.objects.filter(pk=self.action.pk).exists())
        self.assertEqual(self.game.game_tags.count(), 1)

    def test_tag_in_use_cannot_be_deleted_via_queryset(self):
        with self.assertRaises(ProtectedError):
            Tag.objects.filter(name="Action").delete()
        self.assertTrue(Tag.objects.filter(name="Action").exists())

    def test_unused_tag_can_be_deleted(self):
        unused = Tag.objects.create(name="Unused")
        unused.delete()
        self.assertFalse(Tag.objects.filter(name="Unused").exists())

    def test_tag_can_be_retired_after_removing_its_links(self):
        GameTag.objects.filter(tag=self.action).delete()
        self.action.delete()
        self.assertFalse(Tag.objects.filter(name="Action").exists())
        self.assertTrue(Game.objects.filter(pk=self.game.pk).exists())

    def test_deleting_game_removes_its_gametags_but_keeps_the_tag(self):
        other = Game.objects.create(appid=2, name="H")
        GameTag.objects.create(game=other, tag=self.action, votes=1)

        self.game.delete()

        self.assertFalse(GameTag.objects.filter(game_id=1).exists())
        self.assertTrue(Tag.objects.filter(pk=self.action.pk).exists())
        self.assertEqual(list(self.action.games.all()), [other])

    def test_wishlisted_game_cannot_be_deleted(self):
        user = User.objects.create_user(username="alice", password="x")
        WishlistItem.objects.create(user=user, game=self.game)

        with self.assertRaises(ProtectedError):
            self.game.delete()

        self.assertTrue(Game.objects.filter(pk=1).exists())
        self.assertEqual(user.wishlist_items.count(), 1)
        self.assertEqual(self.game.game_tags.count(), 1)

    def test_deleting_user_removes_their_wishlist_but_not_the_game(self):
        user = User.objects.create_user(username="alice", password="x")
        WishlistItem.objects.create(user=user, game=self.game)

        user.delete()

        self.assertFalse(WishlistItem.objects.exists())
        self.assertTrue(Game.objects.filter(pk=1).exists())

    def test_deleting_genre_only_removes_links(self):
        genre = Genre.objects.create(name="RPG")
        self.game.genres.add(genre)
        genre.delete()
        self.assertTrue(Game.objects.filter(pk=1).exists())
        self.assertEqual(self.game.genres.count(), 0)