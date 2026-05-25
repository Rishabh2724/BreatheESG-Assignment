from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("batches", views.ImportBatchViewSet)
router.register("records", views.ActivityRecordViewSet)

urlpatterns = [
    path("auth/token/", obtain_auth_token),   # POST username+password -> {token}
    path("me/", views.me),
    path("summary/", views.summary),
    path("", include(router.urls)),
]
