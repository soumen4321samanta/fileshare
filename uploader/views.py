import os

from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render

from .models import UploadedFile

SESSION_KEY = "sent_files"
MAX_SESSION_HISTORY = 30

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp"}
PDF_EXTS = {".pdf"}
DOC_EXTS = {".doc", ".docx", ".txt", ".rtf", ".odt"}
SHEET_EXTS = {".xls", ".xlsx", ".csv"}
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg"}
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv"}


def file_kind(filename):
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in DOC_EXTS:
        return "doc"
    if ext in SHEET_EXTS:
        return "sheet"
    if ext in ARCHIVE_EXTS:
        return "archive"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return "file"


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

        history = request.session.get(SESSION_KEY, [])
        just_uploaded_ids = []

        for f in files:
            obj = UploadedFile.objects.create(file=f, original_filename=f.name)
            just_uploaded_ids.append(obj.id)
            history.insert(
                0,
                {
                    "id": obj.id,
                    "name": obj.original_filename,
                    "url": obj.file.url,
                    "size": obj.size_display,
                    "kind": file_kind(obj.original_filename),
                    "uploaded_at": obj.uploaded_at.strftime("%d %b, %I:%M %p"),
                },
            )

        request.session[SESSION_KEY] = history[:MAX_SESSION_HISTORY]
        # Stash which IDs were just uploaded so the *next* GET (after the
        # redirect below) can show the "SENT" stamp animation on them once.
        request.session["just_uploaded_ids"] = just_uploaded_ids
        request.session.modified = True

        if files:
            messages.success(request, f"Sent {len(files)} file(s) successfully.")
        return redirect("upload")

    history = request.session.get(SESSION_KEY, [])
    # Pop (read + clear) so the stamp only animates once, right after upload.
    just_uploaded_ids = request.session.pop("just_uploaded_ids", [])
    request.session.modified = True
    return render(
        request,
        "uploader/upload.html",
        {
            "sent_files": history,
            "just_uploaded_ids": just_uploaded_ids,
        },
    )