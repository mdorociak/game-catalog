from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, GameViewSet, GenreViewSet, TagViewSet, WishlistViewSet

router = DefaultRouter()
router.register("games", GameViewSet)
router.register("genres", GenreViewSet)
router.register("categories", CategoryViewSet)
router.register("tags", TagViewSet)
router.register("wishlist", WishlistViewSet, basename="wishlist")

urlpatterns = router.urls