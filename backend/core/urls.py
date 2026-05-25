"""URL configuration. /admin and /api are Django; everything else serves the React SPA."""

from django.conf import settings
from django.contrib import admin
from django.http import HttpResponse, HttpResponseNotFound
from django.urls import include, path, re_path

_INDEX = settings.STATIC_ROOT / "index.html"


def spa(request):
    """Serve the built React index.html for any non-API route (client-side routing).

    The compiled assets are collected into STATIC_ROOT and served by WhiteNoise; this view
    only returns the HTML shell. In local dev (no build yet) it returns a hint instead.
    """
    if _INDEX.exists():
        return HttpResponse(_INDEX.read_bytes())
    return HttpResponseNotFound(
        "Frontend not built. Run the Vite dev server (npm run dev) or build it.")


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("ingest.urls")),
    re_path(r"^(?!api/|admin/|static/).*$", spa),
]
