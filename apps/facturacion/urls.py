from django.urls import path
from .views import lista, nuevo, detalle, anular, consulta_general, descargar_xml

app_name = "facturacion"

urlpatterns = [
    path("", lista, name="lista"),
    path("nuevo/", nuevo, name="nuevo"),
    path("consulta-general/", consulta_general, name="consulta_general"),
    path("<int:pk>/xml/", descargar_xml, name="descargar_xml"),
    path("<int:pk>/", detalle, name="detalle"),
    path("<int:pk>/anular/", anular, name="anular"),
]
