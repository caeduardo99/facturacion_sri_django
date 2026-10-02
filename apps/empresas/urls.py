from django.urls import path
from .views import lista, nuevo, consultar, crear, editar, eliminar

app_name = "empresas"

urlpatterns = [
    path("", lista, name="lista"),
    path("nuevo/", nuevo, name="nuevo"),
    path("consultar/", consultar, name="consultar"),
    path("crear/", crear, name="crear"),
    path("<int:pk>/editar/", editar, name="editar"),
    path("<int:pk>/eliminar/", eliminar, name="eliminar"),
]
