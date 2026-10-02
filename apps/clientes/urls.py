from django.urls import path
from .views import lista
app_name='clientes'; urlpatterns=[path('',lista,name='lista')]
