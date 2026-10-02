from django.urls import path
from .views import lista
app_name='facturacion'; urlpatterns=[path('',lista,name='lista')]
