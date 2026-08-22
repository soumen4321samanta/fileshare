import io
import os
import zipfile

import img2pdf
import pymupdf
from django.http import FileResponse, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from PIL import Image

MAX_UPLOAD_SIZE = 25 * 1024 * 1024  # 25 MB, matches uploader app's limit


def _error(message, status=400):
    return JsonResponse({"error": message}, status=status)


# ---------------------------------------------------------------------------
# JPG -> PDF
# ---------------------------------------------------------------------------
@csrf_exempt
@require_POST
def jpg_to_pdf(request):
    files = request.FILES.getlist("files")
    if not files:
        return _error("Please attach at least one image.")

    image_bytes_list = []
    for f in files:
        if f.size > MAX_UPLOAD_SIZE:
            return _error(f"{f.name} is over the 25MB limit.")
        try:
            img = Image.open(f)
            img.load()
            if img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=92)
            image_bytes_list.append(buf.getvalue())
        except Exception:
            return _error(f"Could not read {f.name} as an image.")

    try:
        pdf_bytes = img2pdf.convert(image_bytes_list)
    except Exception:
        return _error("Could not build the PDF from these images.", 500)

    return FileResponse(
        io.BytesIO(pdf_bytes),
        as_attachment=True,
        filename="converted.pdf",
        content_type="application/pdf",
    )


# ---------------------------------------------------------------------------
# PDF -> JPG  (returns a single JPG for 1-page PDFs, a ZIP for multi-page)
# ---------------------------------------------------------------------------
@csrf_exempt
@require_POST
def pdf_to_jpg(request):
    f = request.FILES.get("file")
    if not f:
        return _error("Please attach a PDF file.")
    if f.size > MAX_UPLOAD_SIZE:
        return _error("File is over the 25MB limit.")

    try:
        doc = pymupdf.open(stream=f.read(), filetype="pdf")
    except Exception:
        return _error("Could not open this file as a PDF.")

    if doc.page_count == 0:
        return _error("This PDF has no pages.")

    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=150)
        images.append(pix.tobytes("jpg"))
    doc.close()

    if len(images) == 1:
        return FileResponse(
            io.BytesIO(images[0]),
            as_attachment=True,
            filename="page.jpg",
            content_type="image/jpeg",
        )

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for i, img_bytes in enumerate(images, start=1):
            zf.writestr(f"page_{i}.jpg", img_bytes)
    zip_buf.seek(0)
    return FileResponse(
        zip_buf,
        as_attachment=True,
        filename="pages.zip",
        content_type="application/zip",
    )


# ---------------------------------------------------------------------------
# JPG compress (target size in KB, best-effort via quality binary search)
# ---------------------------------------------------------------------------
def _compress_image_to_target(img, target_kb):
    target_bytes = max(target_kb, 1) * 1024
    if img.mode in ("RGBA", "P"):
        img = img.convert("RGB")

    def best_at_quality(image):
        """Binary-search JPEG quality for this exact image size. Returns
        (bytes, achieved) - achieved is True only if it actually met target."""
        lo, hi = 5, 95
        best_bytes = None
        while lo <= hi:
            q = (lo + hi) // 2
            buf = io.BytesIO()
            image.save(buf, format="JPEG", quality=q, optimize=True)
            size = buf.tell()
            if size <= target_bytes:
                best_bytes = buf.getvalue()
                lo = q + 1
            else:
                hi = q - 1
        if best_bytes is not None:
            return best_bytes, True
        # Even quality=5 didn't fit - return that as the current best attempt.
        buf = io.BytesIO()
        image.save(buf, format="JPEG", quality=5, optimize=True)
        return buf.getvalue(), False

    result_bytes, achieved = best_at_quality(img)
    if achieved:
        return result_bytes

    # Quality reduction alone wasn't enough (common for busy/detailed photos
    # where even quality=5 is still above the target). Progressively shrink
    # the image dimensions and retry - this is what actually gets very
    # small target sizes on detailed images, since resolution affects file
    # size far more than quality once quality is already low.
    working_img = img
    for _ in range(12):
        w, h = working_img.size
        if w <= 80 or h <= 80:
            break
        working_img = working_img.resize((int(w * 0.85), int(h * 0.85)), Image.LANCZOS)
        result_bytes, achieved = best_at_quality(working_img)
        if achieved:
            return result_bytes

    # Could not hit target even at minimum size - return smallest achieved.
    return result_bytes


@csrf_exempt
@require_POST
def jpg_compress(request):
    f = request.FILES.get("file")
    target_kb = request.POST.get("target_kb")

    if not f:
        return _error("Please attach an image.")
    if f.size > MAX_UPLOAD_SIZE:
        return _error("File is over the 25MB limit.")
    try:
        target_kb = int(target_kb)
        if target_kb < 5:
            return _error("Target size must be at least 5 KB.")
    except (TypeError, ValueError):
        return _error("Please provide a valid target size in KB.")

    try:
        img = Image.open(f)
        img.load()
    except Exception:
        return _error("Could not read this file as an image.")

    result_bytes = _compress_image_to_target(img, target_kb)

    return FileResponse(
        io.BytesIO(result_bytes),
        as_attachment=True,
        filename="compressed.jpg",
        content_type="image/jpeg",
    )


# ---------------------------------------------------------------------------
# PDF compress (target size in KB, best-effort by recompressing embedded images)
# ---------------------------------------------------------------------------
@csrf_exempt
@require_POST
def pdf_compress(request):
    f = request.FILES.get("file")
    target_kb = request.POST.get("target_kb")

    if not f:
        return _error("Please attach a PDF file.")
    if f.size > MAX_UPLOAD_SIZE:
        return _error("File is over the 25MB limit.")
    try:
        target_kb = int(target_kb)
        if target_kb < 5:
            return _error("Target size must be at least 5 KB.")
    except (TypeError, ValueError):
        return _error("Please provide a valid target size in KB.")

    target_bytes = target_kb * 1024
    original_bytes = f.read()

    def try_compress(quality, scale):
        """Recompress every embedded image at the given JPEG quality, first
        downscaling by `scale` (1.0 = original size). Also subsets embedded
        fonts to only the glyphs actually used - this is what actually
        shrinks text-heavy PDFs (like resumes) that have little or no
        image data, where the size mostly comes from embedded font files."""
        doc = pymupdf.open(stream=original_bytes, filetype="pdf")
        for page in doc:
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                try:
                    base = doc.extract_image(xref)
                    img = Image.open(io.BytesIO(base["image"]))
                    if img.mode in ("RGBA", "P"):
                        img = img.convert("RGB")
                    if scale < 1.0:
                        w, h = img.size
                        new_w, new_h = max(int(w * scale), 40), max(int(h * scale), 40)
                        img = img.resize((new_w, new_h), Image.LANCZOS)
                    buf = io.BytesIO()
                    img.save(buf, format="JPEG", quality=quality, optimize=True)
                    # NOTE: page.replace_image() (not doc.update_stream()) is
                    # required here - it correctly updates the image's filter/
                    # colorspace metadata to match the new JPEG bytes. Using
                    # update_stream() directly leaves the old metadata in
                    # place and renders as a solid black page.
                    page.replace_image(xref, stream=buf.getvalue())
                except Exception:
                    continue
        try:
            doc.subset_fonts()
        except Exception:
            pass
        out_buf = io.BytesIO()
        doc.save(out_buf, garbage=4, deflate=True, deflate_fonts=True, clean=True)
        doc.close()
        return out_buf.getvalue()

    def count_images():
        doc = pymupdf.open(stream=original_bytes, filetype="pdf")
        total = sum(len(page.get_images(full=True)) for page in doc)
        doc.close()
        return total

    best_result = None
    try:
        has_images = count_images() > 0

        # Pass 1: reduce JPEG quality only (fast, keeps full resolution).
        # Also subsets/deflates fonts every time - this is what shrinks
        # text-heavy PDFs, independent of the image quality setting.
        for quality in (80, 60, 40, 25, 15, 8):
            result_bytes = try_compress(quality, 1.0)
            best_result = result_bytes
            if len(result_bytes) <= target_bytes:
                break
            if not has_images:
                # No images to recompress - every quality setting gives the
                # same result, so don't bother repeating it.
                break

        if has_images and (best_result is None or len(best_result) > target_bytes):
            # Pass 2: quality alone wasn't enough (common for busy/detailed
            # scans) - progressively shrink image resolution too, since that
            # affects size far more once quality is already low.
            scale = 1.0
            for _ in range(10):
                scale *= 0.85
                result_bytes = try_compress(8, scale)
                best_result = result_bytes
                if len(result_bytes) <= target_bytes:
                    break
    except Exception:
        return _error("Could not open this file as a PDF.")

    if best_result is None:
        return _error("Could not compress this PDF.", 500)

    return FileResponse(
        io.BytesIO(best_result),
        as_attachment=True,
        filename="compressed.pdf",
        content_type="application/pdf",
    )


# ---------------------------------------------------------------------------
# PDF -> Word
# ---------------------------------------------------------------------------
@csrf_exempt
@require_POST
def pdf_to_word(request):
    f = request.FILES.get("file")
    if not f:
        return _error("Please attach a PDF file.")
    if f.size > MAX_UPLOAD_SIZE:
        return _error("File is over the 25MB limit.")

    import tempfile
    from pdf2docx import Converter
    from docx import Document as DocxDocument

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
        tmp_pdf.write(f.read())
        tmp_pdf_path = tmp_pdf.name

    tmp_docx_path = tmp_pdf_path.replace(".pdf", ".docx")

    try:
        cv = Converter(tmp_pdf_path)
        cv.convert(tmp_docx_path)
        cv.close()

        with open(tmp_docx_path, "rb") as docx_file:
            docx_bytes = docx_file.read()
    except Exception:
        return _error(
            "Could not produce a valid Word file from this PDF. This can "
            "happen with PDFs that have unusual fonts, layouts, or were "
            "generated by certain tools.",
            500,
        )
    finally:
        for path in (tmp_pdf_path, tmp_docx_path):
            try:
                os.remove(path)
            except OSError:
                pass

    return FileResponse(
        io.BytesIO(docx_bytes),
        as_attachment=True,
        filename="converted.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )