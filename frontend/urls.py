from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("jpg-to-pdf/", views.jpg_to_pdf_page, name="jpg_to_pdf"),
    path("pdf-to-jpg/", views.pdf_to_jpg_page, name="pdf_to_jpg"),
    path("jpg-compress/", views.jpg_compress_page, name="jpg_compress"),
    path("pdf-compress/", views.pdf_compress_page, name="pdf_compress"),
    path("pdf-to-word/", views.pdf_to_word_page, name="pdf_to_word"),
    path("merge-pdf/", views.merge_pdf_page, name="merge_pdf"),
]