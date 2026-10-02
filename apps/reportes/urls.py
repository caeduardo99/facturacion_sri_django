from django.urls import path
from .views import index
app_name='reportes'; urlpatterns=[path('',index,name='index')]
