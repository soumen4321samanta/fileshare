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


def _repair_missing_docx_styles(docx_bytes):
    """pdf2docx sometimes references a paragraph/character/table style (most
    commonly 'Hyperlink', when the source PDF has clickable links) without
    actually defining it in styles.xml. LibreOffice/Google Docs tolerate
    this silently, but Microsoft Word's stricter validator refuses to open
    the file at all ("problems with the contents"). This patches in a
    definition for any referenced-but-missing style so Word opens it fine.
    """
    from lxml import etree

    W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

    zin = zipfile.ZipFile(io.BytesIO(docx_bytes))
    names = zin.namelist()
    data = {n: zin.read(n) for n in names}

    if "word/styles.xml" not in data or "word/document.xml" not in data:
        return docx_bytes

    styles_root = etree.fromstring(data["word/styles.xml"])
    defined = set(s.get(W + "styleId") for s in styles_root.findall("w:style", ns))

    doc_root = etree.fromstring(data["word/document.xml"])
    tag_to_type = {"pStyle": "paragraph", "rStyle": "character", "tblStyle": "table"}
    missing = {}
    for tag, style_type in tag_to_type.items():
        for el in doc_root.findall(f".//w:{tag}", ns):
            style_id = el.get(W + "val")
            if style_id and style_id not in defined:
                missing[style_id] = style_type

    if not missing:
        return docx_bytes

    known = {
        "Hyperlink": (
            '<w:style w:type="character" w:styleId="Hyperlink">'
            '<w:name w:val="Hyperlink"/><w:basedOn w:val="DefaultParagraphFont"/>'
            '<w:uiPriority w:val="99"/><w:unhideWhenUsed/>'
            '<w:rPr><w:color w:val="0563C1" w:themeColor="hyperlink"/><w:u w:val="single"/></w:rPr>'
            "</w:style>"
        ),
    }

    styles_str = data["word/styles.xml"].decode("utf-8")
    injected = []
    for style_id, style_type in missing.items():
        if style_id in known:
            injected.append(known[style_id])
        else:
            injected.append(
                f'<w:style w:type="{style_type}" w:styleId="{style_id}">'
                f'<w:name w:val="{style_id}"/></w:style>'
            )
    styles_str = styles_str.replace("</w:styles>", "".join(injected) + "</w:styles>")
    data["word/styles.xml"] = styles_str.encode("utf-8")

    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for name, content in data.items():
            zout.writestr(name, content)
    return out.getvalue()




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

        docx_bytes = _repair_missing_docx_styles(docx_bytes)

        # Sanity-check the file is actually a valid, openable .docx before
        # sending it back - pdf2docx can occasionally produce a file that
        # "succeeds" with no exception but is malformed enough that Word
        # refuses to open it. Catching that here means the person gets a
        # clear error instead of a file that looks fine but is broken.
        DocxDocument(io.BytesIO(docx_bytes))
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



# ---------------------------------------------------------------------------
# Merge PDF (combine multiple PDFs into one, in the order they're given)
# ---------------------------------------------------------------------------
@csrf_exempt
@require_POST
def merge_pdf(request):
    files = request.FILES.getlist("files")
    if len(files) < 2:
        return _error("Please attach at least two PDF files to merge.")

    total_size = sum(f.size for f in files)
    if total_size > MAX_UPLOAD_SIZE:
        return _error("Combined file size is over the 25MB limit.")

    merged = pymupdf.open()
    try:
        for f in files:
            src = pymupdf.open(stream=f.read(), filetype="pdf")
            merged.insert_pdf(src)
            src.close()
    except Exception:
        merged.close()
        return _error(
            "Could not merge these files - make sure every file is a valid PDF."
        )

    if merged.page_count == 0:
        merged.close()
        return _error("The merged PDF has no pages.")

    out_buf = io.BytesIO()
    merged.save(out_buf)
    merged.close()

    return FileResponse(
        io.BytesIO(out_buf.getvalue()),
        as_attachment=True,
        filename="merged.pdf",
        content_type="application/pdf",
    )


# ---------------------------------------------------------------------------
# Delete pages from a PDF
# ---------------------------------------------------------------------------
def _parse_page_spec(spec, total_pages):
    """Parse a spec like '2,4-6' (1-indexed, as shown to the person) into a
    set of 0-indexed page numbers. Out-of-range numbers are silently
    ignored; malformed text raises ValueError."""

    result=set()
    parts=[p.strip() for p in spec.split(",") if p.strip()]

    if not parts:
        raise ValueError("empty")
    for part in parts:
        if "-" in part:
            start_str,end_str=part.split("-",1)
            start,end=int(start_str),int(end_str)
            if start>end:
                start,end=end,start
            for p in range(start,end+1):
                if 1<= p <= total_pages:
                    result.add(p-1)
        else:
            p=int(part)
            if 1<= p <= total_pages:
                result.add(p-1)
    return result

@csrf_exempt
@require_POST
def pdf_delete_pages(request):
    f=request.FILES.get("file")
    pages_spec=request.POST.get("pages","")

    if not f:
        return _error("Please attach a PDF file.")
    if f.size>MAX_UPLOAD_SIZE:
        return _error("File is over the 25MB Limit.")

    if not pages_spec.strip():
        return _error("Please enter which page(s) to delete, e.g. '2,4-6")
    try:
        doc=pymupdf.open(stream=f.read(),filetype="pdf")
    except Exception:
        return _error("Could not open this file as a PDF.")

    total_pages=doc.page_count
    try:
        to_delete=_parse_page_spec(pages_spec,total_pages)
    except ValueError:
        doc.close()
        return _error("Could not parse the page specification. Use a format like '2,4-6'.")

    if not to_delete:
        doc.close()
        return _error("No valid pages to delete were specified.")
    keep = [i for i in range(total_pages) if i not in to_delete]

    if not keep:
        doc.close()
        return _error("Cannot delete all pages - at least one page must remain.")

    doc.select(keep)
    out_buf=io.BytesIO()
    doc.save(out_buf)
    doc.close()

    return FileResponse(
        io.BytesIO(out_buf.getvalue()),
        as_attachment=True,
        filename="edited.pdf",
        content_type="application/pdf",
    )


@csrf_exempt
@require_POST
def pdf_page_count(request):
    """Small helper the frontend calls right after a file is selected, so
    it can show 'This PDF has N pages' before the person types which ones
    to delete."""
    f = request.FILES.get("file")
    if not f:
        return _error("Please attach a PDF file.")
    try:
        doc = pymupdf.open(stream=f.read(), filetype="pdf")
        count = doc.page_count
        doc.close()
    except Exception:
        return _error("Could not open this file as a PDF.")
    return JsonResponse({"pages": count})




MAX_THUMB_PAGES = 60


@csrf_exempt
@require_POST
def pdf_thumbnails(request):
    """Renders every page as a small JPEG thumbnail (base64 data URI) so the
    frontend can show a visual page picker instead of asking for typed page
    numbers."""
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
        doc.close()
        return _error("This PDF has no pages.")

    if doc.page_count > MAX_THUMB_PAGES:
        total_pages = doc.page_count
        doc.close()
        return _error(
            f"This PDF has {total_pages} pages - previews are limited to "
            f"{MAX_THUMB_PAGES} pages to keep things fast."
        )

    import base64

    pages = []
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=60)
        img_bytes = pix.tobytes("jpg")
        b64 = base64.b64encode(img_bytes).decode("ascii")
        pages.append({"page": i + 1, "thumbnail": f"data:image/jpeg;base64,{b64}"})
    doc.close()

    return JsonResponse({"pages": pages, "total": len(pages)})






@csrf_exempt
@require_POST
def pdf_reorder_pages(request):
    f=request.FILES.get("file")
    order_spec=request.POST.get("order","")

    if not f:
        return _error("Please attach a PDF file.")
    if f.size>MAX_UPLOAD_SIZE:
        return _error("File is over the 25MB Limit.")
    if not order_spec.strip():
        return _error("Please provide the new page order.")

    try:
        doc=pymupdf.open(stream=f.read(),filetype="pdf")
    except Exception:
        return _error("Could not open this file as a PDF.")

    total_pages=doc.page_count

    try:
        order=[int(x.strip()) for x in order_spec.split(",") if x.strip()]
    except ValueError:
        doc.close()
        return _error("Invalid page Order.")

    if sorted(order)!= list(range(1,total_pages + 1)):
        doc.close()
        return _error("The new order must include every page exactly one.")
    zero_indexed=[p - 1 for p in order ]
    doc.select(zero_indexed)
    out_buf=io.BytesIO()
    doc.save(out_buf)
    doc.close()

    return FileResponse(
        io.BytesIO(out_buf.getvalue()),
        as_attachment=True,
        filename="reordered.pdf",
        content_type="application/pdf",
    )



@csrf_exempt
@require_POST
def pdf_rotate_pages(request):
    f=request.FILES.get("file")
    angles_spec=request.POST.get("angles","")

    if not f:
        return _error("Please attach a PDF file.")
    if f.size>MAX_UPLOAD_SIZE:
        return _error("File is over the 25MB limit.")
    if not angles_spec.strip():
        return _error("Please Provide rotation angles for each page,")

    try:
        doc=pymupdf.open(stream=f.read(),filetype="pdf")
    except Exception:
        return _error("Could not open the file as a PDF.")

    total_pages=doc.page_count

    try:
        angles=[int(x.strip()) for x in angles_spec.split(",")]
    except ValueError:
        doc.close()
        return _error("Invalid rotation angles.")

    if len(angles)!=total_pages:
        doc.close()
        return _error("Rotation data doesn't match the number of pages.")

    if any(a not in (0,90,180,270) for a in angles):
        doc.close()
        return _error("Angles must be 0,90,180 or 270 degrees")

    if all(a==0 for a in angles):
        doc.close()
        return _error("No pages were rotated -nothing to save.")


    for i, page in enumerate(doc):
        delta=angles[i]
        if delta:
            page.set_rotation((page.rotation + delta) % 360)

    out_buf=io.BytesIO()
    doc.save(out_buf)
    doc.close()

    return FileResponse(
        io.BytesIO(out_buf.getvalue()),
        as_attachment=True,
        filename="rotated.pdf",
        content_type="application/pdf",
    )


MAX_OCR_PAGES=30

@csrf_exempt
@require_POST
def pdf_ocr(request):
    """Makes a scanned/image PDF searchable by running OCR on every page
    and embedding an invisible text layer, using PyMuPDF's built-in
    pdfocr_tobytes() (backed by Tesseract). The visual appearance is
    unchanged - only text becomes selectable/searchable/copyable."""

    f=request.FILES.get("file")
    if not f:
        return _error("Please attach a PDF file.")
    if f.size>MAX_UPLOAD_SIZE:
        return _error("File is over the 25MB limit.")

    try:
        doc=pymupdf.open(stream=f.read(),filetype="pdf")
    except Exception:
        return _error("Could not open this file as a PDF.")


    if doc.page_count==0:
        doc.close()
        return _error("This PDF has no pages.")

    if doc.page_count>MAX_OCR_PAGES:
        total_pages=doc.page_count
        doc.close()
        return _error(
            f"This PDF has {total_pages} pages - OCR is limited to {MAX_OCR_PAGES} pages."
        )

    out_doc=pymupdf.open()
    try:
        for page in doc:
            pix=page.get_pixmap(dpi=200)
            ocr_bytes=pix.pdfocr_tobytes(language="eng")
            ocr_page_doc=pymupdf.open("pdf",ocr_bytes)
            out_doc.insert_pdf(ocr_page_doc)
            ocr_page_doc.close()
    except Exception:
        doc.close()
        out_doc.close()
        return _error("Could not perform OCR on this PDF.",500)

    doc.close()
    out_buf=io.BytesIO()
    out_doc.save(out_buf)
    out_doc.close()

    return FileResponse(
        io.BytesIO(out_buf.getvalue()),
        as_attachment=True,
        filename="ocr.pdf",
        content_type="application/pdf",
    )
    
            