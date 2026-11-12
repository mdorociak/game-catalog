from django.conf import settings
from django.db import models


class NamedModel(models.Model):

    name = models.CharField(max_length=255, unique=True)

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


class Genre(NamedModel):
    pass


class Category(NamedModel):
    class Meta(NamedModel.Meta):
        verbose_name_plural = "categories"


class Tag(NamedModel):
    pass


class Game(models.Model):
    appid = models.PositiveIntegerField(primary_key=True)
    name = models.CharField(max_length=512, db_index=True)
    release_date = models.DateField(null=True, blank=True)
    price = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    positive = models.PositiveIntegerField(default=0)
    negative = models.PositiveIntegerField(default=0)
    required_age = models.PositiveSmallIntegerField(default=0)

    genres = models.ManyToManyField(Genre, related_name="games", blank=True)
    categories = models.ManyToManyField(
        Category, related_name="games", blank=True
    )
    tags = models.ManyToManyField(
        Tag, through="GameTag", related_name="games", blank=True
    )

    class Meta:
        ordering = ["appid"]

    def __str__(self):
        return self.name

    @property
    def is_free(self):
        return self.price is not None and self.price == 0

# No separate index: unique_game_tag (game, tag) already covers lookups by game.

class GameTag(models.Model):
    game = models.ForeignKey(
        Game, 
        on_delete=models.CASCADE, 
        related_name="game_tags",
        db_index=False
    )
    tag = models.ForeignKey(Tag, on_delete=models.PROTECT)
    votes = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["game", "tag"], name="unique_game_tag"
            ),
        ]
        ordering = ["-votes", "id"]

    def __str__(self):
        return f"{self.game} · {self.tag} ({self.votes})"


class WishlistItem(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
        db_index=False
    )
    game = models.ForeignKey(Game, on_delete=models.PROTECT)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "game"], name="unique_wishlist_item"
            ),
        ]
        ordering = ["-added_at", "-id"]

    def __str__(self):
        return f"{self.user} → {self.game}"