from django.db.models import Exists, OuterRef
from django_filters import rest_framework as filters
from rest_framework.filters import OrderingFilter

from .models import Game, GameTag


def _has_name(link_model, relation, value):
    return Exists(
        link_model.objects.filter(
            game_id=OuterRef("pk"), **{f"{relation}__name__iexact": value}
        )
    )


class GameFilter(filters.FilterSet):
    genre = filters.CharFilter(method="filter_genre")
    category = filters.CharFilter(method="filter_category")
    tag = filters.CharFilter(method="filter_tag")
    min_price = filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = filters.NumberFilter(field_name="price", lookup_expr="lte")
    is_free = filters.BooleanFilter(method="filter_is_free")
    released_after = filters.DateFilter(field_name="release_date", lookup_expr="gte")
    released_before = filters.DateFilter(field_name="release_date", lookup_expr="lte")

    class Meta:
        model = Game
        fields = [] 

    def filter_genre(self, queryset, name, value):
        return queryset.filter(_has_name(Game.genres.through, "genre", value))

    def filter_category(self, queryset, name, value):
        return queryset.filter(_has_name(Game.categories.through, "category", value))

    def filter_tag(self, queryset, name, value):
        return queryset.filter(_has_name(GameTag, "tag", value))

    def filter_is_free(self, queryset, name, value):
        return queryset.filter(price=0) if value else queryset.filter(price__gt=0)


class StableOrderingFilter(OrderingFilter):
    def get_ordering(self, request, queryset, view):
        ordering = super().get_ordering(request, queryset, view)
        if ordering and not {"pk", "-pk"} & set(ordering):
            ordering = [*ordering, "pk"]
        return ordering