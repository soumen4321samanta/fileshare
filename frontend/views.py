from django.shortcuts import render


def home(request):
    return render(request, "frontend/home.html", {"active": "home"})


def jpg_to_pdf_page(request):
    return render(request, "frontend/jpg_to_pdf.html", {"active": "jpg_to_pdf"})


def pdf_to_jpg_page(request):
    return render(request, "frontend/pdf_to_jpg.html", {"active": "pdf_to_jpg"})


def jpg_compress_page(request):
    return render(request, "frontend/jpg_compress.html", {"active": "jpg_compress"})


def pdf_compress_page(request):
    return render(request, "frontend/pdf_compress.html", {"active": "pdf_compress"})


def pdf_to_word_page(request):
    return render(request, "frontend/pdf_to_word.html", {"active": "pdf_to_word"})


def merge_pdf_page(request):
    return render(request, "frontend/merge_pdf.html", {"active": "merge_pdf"})


def pdf_delete_pages_page(request):
    return render(request, "frontend/pdf_delete_pages.html", {"active": "pdf_delete_pages"})


def reorder_pages_page(request):
    return render(request,"frontend/reorder_pages.html",{"active":"reorder_pages"})


def rotate_pages_page(request):
    return render(request,"frontend/rotate_pages.html",{"active":"rotate_pages"})


def ocr_page(request):
    return render(request,"frontend/ocr.html",{"active":"ocr"})