from django.contrib import admin
from django.utils.html import format_html

from .models import UploadedFile


@admin.register(UploadedFile)
class UploadedFileAdmin(admin.ModelAdmin):
    list_display = ("original_filename", "uploaded_at", "size_display", "download_link")
    readonly_fields = ("original_filename", "uploaded_at", "download_link")
    ordering = ("-uploaded_at",)
    search_fields = ("original_filename",)

    def download_link(self, obj):
        if obj.file:
            return format_html('<a href="{}" target="_blank">Download</a>', obj.file.url)
        return "-"

    download_link.short_description = "File"
