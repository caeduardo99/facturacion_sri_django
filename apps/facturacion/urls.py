from django.urls import path
from .views import lista, nuevo, detalle, anular, consulta_general, descargar_xml, descargar_ride, catalogo_transacciones, transaccion_form, transaccion_eliminar, configuracion_menus, cambiar_estado_transaccion, ofertas, oferta_detalle_json

app_name = "facturacion"

urlpatterns = [
    path("", lista, name="lista"),
    path("ofertas/", ofertas, name="ofertas"),
    path("ofertas/<int:pk>/json/", oferta_detalle_json, name="oferta_detalle_json"),
    path("nuevo/", nuevo, name="nuevo"),
    path("consulta-general/", consulta_general, name="consulta_general"),
    path("<int:pk>/cambiar-estado-transaccion/", cambiar_estado_transaccion, name="cambiar_estado_transaccion"),
    path("configuracion-menus/", configuracion_menus, name="configuracion_menus"),
    path("catalogo-transacciones/", catalogo_transacciones, name="catalogo_transacciones"),
    path("catalogo-transacciones/nuevo/", transaccion_form, name="transaccion_nuevo"),
    path("catalogo-transacciones/<int:pk>/editar/", transaccion_form, name="transaccion_editar"),
    path("catalogo-transacciones/<int:pk>/eliminar/", transaccion_eliminar, name="transaccion_eliminar"),
    path("<int:pk>/xml/", descargar_xml, name="descargar_xml"),
    path("<int:pk>/ride/", descargar_ride, name="descargar_ride"),
    path("<int:pk>/", detalle, name="detalle"),
    path("<int:pk>/anular/", anular, name="anular"),
]
