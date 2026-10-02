from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth.views import LoginView, LogoutView
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("accounts/logout/", LogoutView.as_view(), name="logout"),
    path("", include("apps.core.urls")),
    path("empresas/", include("apps.empresas.urls")),
    path("clientes/", include("apps.clientes.urls")),
    path("productos/", include("apps.productos.urls")),
    path("facturacion/", include("apps.facturacion.urls")),
    path("sri/", include("apps.sri.urls")),
    path("reportes/", include("apps.reportes.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
