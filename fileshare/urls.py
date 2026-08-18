from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("uploader.urls")),
]

# Serve uploaded files. Django doesn't normally serve MEDIA when DEBUG=False,
# but for this small personal tool (low traffic, not public-scale) we serve
# media files always so the admin dashboard's download links work on Render
# without needing a separate cloud storage service.
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
