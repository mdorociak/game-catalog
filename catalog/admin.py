from django.contrib import admin

from .models import Category, Game, GameTag, Genre, Tag, WishlistItem


@admin.register(Genre, Category, Tag)
class NamedAdmin(admin.ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]


class GameTagInline(admin.TabularInline):
    model = GameTag
    extra = 1
    autocomplete_fields = ["tag"]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("game", "tag")


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ["appid", "name", "release_date", "price", "positive"]
    search_fields = ["name"] 
    list_filter = ["genres"]
    autocomplete_fields = ["genres", "categories"]
    inlines = [GameTagInline]


@admin.register(WishlistItem)
class WishlistItemAdmin(admin.ModelAdmin):
    list_display = ["user", "game", "added_at"]
    list_select_related = ["user", "game"]
    autocomplete_fields = ["user", "game"]