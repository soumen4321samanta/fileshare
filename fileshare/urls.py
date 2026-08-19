from django.conf import settings
from django.contrib import admin
from django.urls import path, re_path, include
from django.views.static import serve as serve_static

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("uploader.urls")),
]

# Serve uploaded files. NOTE: Django's usual static()/static.static() helper
# only serves files when settings.DEBUG is True - it silently no-ops
# otherwise. Since this app runs with DEBUG=False on Render, we register the
# view directly instead so download links keep working in production.
urlpatterns += [
    re_path(
        r"^media/(?P<path>.*)$",
        serve_static,
        {"document_root": settings.MEDIA_ROOT},
    ),
]