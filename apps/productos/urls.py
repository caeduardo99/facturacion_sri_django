from django.urls import path
from .views import lista
app_name='productos'; urlpatterns=[path('',lista,name='lista')]
