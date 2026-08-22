from django.urls import path

from . import views

urlpatterns = [
    path("jpg-to-pdf/", views.jpg_to_pdf, name="api_jpg_to_pdf"),
    path("pdf-to-jpg/", views.pdf_to_jpg, name="api_pdf_to_jpg"),
    path("jpg-compress/", views.jpg_compress, name="api_jpg_compress"),
    path("pdf-compress/", views.pdf_compress, name="api_pdf_compress"),
    path("pdf-to-word/", views.pdf_to_word, name="api_pdf_to_word"),
]