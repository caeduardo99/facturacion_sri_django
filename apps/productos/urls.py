from django.urls import path
from .views import lista, nuevo, editar, eliminar

app_name = "productos"

urlpatterns = [
    path("", lista, name="lista"),
    path("nuevo/", nuevo, name="nuevo"),
    path("<int:pk>/editar/", editar, name="editar"),
    path("<int:pk>/eliminar/", eliminar, name="eliminar"),
]
