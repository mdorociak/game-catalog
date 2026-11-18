from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, GameViewSet, GenreViewSet, TagViewSet

router = DefaultRouter()
router.register("games", GameViewSet)
router.register("genres", GenreViewSet)
router.register("categories", CategoryViewSet)
router.register("tags", TagViewSet)

urlpatterns = router.urls