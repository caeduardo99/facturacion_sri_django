from django.urls import path
from .views import lista

app_name = "empresas"
urlpatterns = [path("", lista, name="lista")]
