from django.db import IntegrityError, transaction
from django.db.models import Count, Prefetch
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .filters import GameFilter
from .models import Category, Game, GameTag, Genre, Tag, WishlistItem
from .serializers import (
    DUPLICATE_WISHLIST_MESSAGE,
    GameDetailSerializer,
    GameListSerializer,
    LookupSerializer,
    SimilarGameSerializer,
    WishlistItemSerializer,
)

SIMILAR_DEFAULT_LIMIT = 10
SIMILAR_MAX_LIMIT = 50


class GameViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Game.objects.all()
    lookup_value_regex = r"\d+"  
    filterset_class = GameFilter
    search_fields = ["name"]  
    ordering_fields = ["name", "release_date", "price", "positive"]

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.action == "similar":
            return queryset
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
        if self.action == "similar":
            return SimilarGameSerializer
        return GameListSerializer

    @action(detail=True)
    def similar(self, request, pk=None):
        limit = self._similar_limit(request)
        game = self.get_object()  

        similar = (
            Game.objects
            .filter(tags__in=game.game_tags.values("tag"))
            .exclude(pk=game.pk)
            .annotate(shared_tags=Count("tags"))
            .order_by("-shared_tags", "-positive", "appid")
            .prefetch_related("genres")[:limit]
        )
        return Response(self.get_serializer(similar, many=True).data)

    @staticmethod
    def _similar_limit(request):
        raw = request.query_params.get("limit")
        if raw is None:
            return SIMILAR_DEFAULT_LIMIT
        try:
            limit = int(raw)
        except ValueError:
            limit = 0
        if limit < 1:
            raise ValidationError({"limit": ["Must be a positive whole number."]})
        return min(limit, SIMILAR_MAX_LIMIT)


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


class WishlistViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.DestroyModelMixin,
    viewsets.GenericViewSet,
):

    serializer_class = WishlistItemSerializer
    permission_classes = [IsAuthenticated]  
    lookup_value_regex = r"\d+"
    pagination_class = None
    filter_backends = [] 

    def get_queryset(self):
        return WishlistItem.objects.filter(user=self.request.user).select_related("game")

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise ValidationError({"non_field_errors": [DUPLICATE_WISHLIST_MESSAGE]})