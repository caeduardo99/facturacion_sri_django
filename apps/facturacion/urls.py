from django.urls import path
from .views import lista, nuevo, detalle, anular

app_name = "facturacion"

urlpatterns = [
    path("", lista, name="lista"),
    path("nuevo/", nuevo, name="nuevo"),
    path("<int:pk>/", detalle, name="detalle"),
    path("<int:pk>/anular/", anular, name="anular"),
]
