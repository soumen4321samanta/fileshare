import os
import uuid

from django.db import models


def upload_path(instance, filename):
    """Store files under media/uploads/<uuid>_<original-filename>
    so two people uploading 'photo.jpg' never overwrite each other."""
    ext = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4().hex}{ext}"
    return os.path.join("uploads", unique_name)


class UploadedFile(models.Model):
    file = models.FileField(upload_to=upload_path)
    original_filename = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.original_filename or self.file.name

    def save(self, *args, **kwargs):
        if not self.original_filename and self.file:
            self.original_filename = os.path.basename(self.file.name)
        super().save(*args, **kwargs)

    @property
    def size_display(self):
        try:
            size = self.file.size
        except (FileNotFoundError, ValueError):
            return "-"
        for unit in ["B", "KB", "MB", "GB"]:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class SiteSettings(models.Model):
    site_name=models.CharField(max_length=50,default="Filoo")
    tagline=models.CharField(max_length=200,default="Every file tool, in one place.")
    logo=models.ImageField(upload_to="site/",blank=True,null=True)

    class Meta:
        verbose_name="Site Settings"
        verbose_name_plural="Site Settings"

    def __str__(self):
        return self.site_name

    def save(self, *args,**kwargs):
        self.pk=1
        super().save(*args,**kwargs)

    @classmethod
    def load(cls):
        obj,created=cls.objects.get_or_create(pk=1)
        return obj
    
