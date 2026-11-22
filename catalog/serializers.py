from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from .models import Game, GameTag, WishlistItem

DUPLICATE_WISHLIST_MESSAGE = "This game is already on your wishlist."


class GameListSerializer(serializers.ModelSerializer):
    genres = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    is_free = serializers.BooleanField(read_only=True)

    class Meta:
        model = Game
        fields = [
            "appid", "name", "release_date", "price", "is_free",
            "positive", "negative", "genres",
        ]


class GameTagSerializer(serializers.ModelSerializer):
    name = serializers.CharField(source="tag.name")

    class Meta:
        model = GameTag
        fields = ["name", "votes"]


class GameDetailSerializer(GameListSerializer):
    categories = serializers.SlugRelatedField(many=True, read_only=True, slug_field="name")
    tags = GameTagSerializer(source="game_tags", many=True, read_only=True)

    class Meta(GameListSerializer.Meta):
        fields = GameListSerializer.Meta.fields + ["required_age", "categories", "tags"]


class SimilarGameSerializer(GameListSerializer):
    shared_tags = serializers.IntegerField(read_only=True)

    class Meta(GameListSerializer.Meta):
        fields = GameListSerializer.Meta.fields + ["shared_tags"]


class WishlistItemSerializer(serializers.ModelSerializer):
    user = serializers.HiddenField(default=serializers.CurrentUserDefault())
    game_name = serializers.CharField(source="game.name", read_only=True)

    class Meta:
        model = WishlistItem
        fields = ["id", "user", "game", "game_name", "added_at"]
        read_only_fields = ["added_at"]
        validators = [
            UniqueTogetherValidator(
                queryset=WishlistItem.objects.all(),
                fields=["user", "game"],
                message=DUPLICATE_WISHLIST_MESSAGE,
            ),
        ]


class LookupSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    game_count = serializers.IntegerField(read_only=True)