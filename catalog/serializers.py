from rest_framework import serializers

from .models import Game, GameTag


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


class LookupSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    name = serializers.CharField(read_only=True)
    game_count = serializers.IntegerField(read_only=True)