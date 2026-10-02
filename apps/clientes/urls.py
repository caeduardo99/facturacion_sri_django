from django.urls import path
from .views import lista, nuevo, consultar, crear

app_name = "clientes"

urlpatterns = [
    path("", lista, name="lista"),
    path("nuevo/", nuevo, name="nuevo"),
    path("consultar/", consultar, name="consultar"),
    path("crear/", crear, name="crear"),
]