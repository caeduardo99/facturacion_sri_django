from django.urls import path
from .views import estado
app_name='sri'; urlpatterns=[path('estado/',estado,name='estado')]
