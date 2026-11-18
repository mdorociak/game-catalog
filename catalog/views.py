from django.db.models import Count, Prefetch
from rest_framework import mixins, viewsets

from .filters import GameFilter
from .models import Category, Game, GameTag, Genre, Tag
from .serializers import GameDetailSerializer, GameListSerializer, LookupSerializer


class GameViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Game.objects.all()
    lookup_value_regex = r"\d+" 
    filterset_class = GameFilter
    search_fields = ["name"] 
    ordering_fields = ["name", "release_date", "price", "positive"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "retrieve":
            return queryset.prefetch_related(
                "genres",
                "categories",
                Prefetch("game_tags", queryset=GameTag.objects.select_related("tag")),
            )
        return queryset.prefetch_related("genres")

    def get_serializer_class(self):
        if self.action == "retrieve":
            return GameDetailSerializer
        return GameListSerializer


def _with_game_count(model):
    return model.objects.annotate(game_count=Count("games")).order_by("-game_count", "name")


class LookupViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = LookupSerializer


class GenreViewSet(LookupViewSet):
    queryset = _with_game_count(Genre)


class CategoryViewSet(LookupViewSet):
    queryset = _with_game_count(Category)


class TagViewSet(LookupViewSet):
    queryset = _with_game_count(Tag)