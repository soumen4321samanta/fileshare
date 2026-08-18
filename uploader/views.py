from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from .models import UploadedFile


def upload_view(request):
    if request.method == "POST":
        files = request.FILES.getlist("file")

        if not files:
            messages.error(request, "Please choose at least one file first.")
            return redirect("upload")

        too_big = [f.name for f in files if f.size > settings.MAX_UPLOAD_SIZE]
        if too_big:
            limit_mb = settings.MAX_UPLOAD_SIZE // (1024 * 1024)
            messages.error(
                request,
                f"These files are over the {limit_mb}MB limit and were not "
                f"uploaded: {', '.join(too_big)}",
            )
            files = [f for f in files if f.size <= settings.MAX_UPLOAD_SIZE]

        for f in files:
            UploadedFile.objects.create(file=f, original_filename=f.name)

        if files:
            messages.success(
                request,
                f"Uploaded {len(files)} file(s) successfully. Thank you!",
            )
        return redirect("upload")

    return render(request, "uploader/upload.html")
