from django.urls import path

from . import views

urlpatterns=[
    path("",views.home,name="home"),
    path("jpg-to-pdf/",views.jpg_to_pdf,name="jpg-to-pdf"),
    path("pdf-to-jpg/",views.pdf_to_jpg,name="pdf-to-jpg"),
    path("jpg-compress/",views.jpg_compress_page,name="jpg-compress-page"),
    path("pdf-compress/",views.pdf_compress_page,name="pdf-compress-page"),
    path("pdf-to-word/",views.pdf_to_word,name="pdf-to-word"),
]