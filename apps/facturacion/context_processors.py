from apps.facturacion.models import TipoTransaccion


def menus_facturacion(request):
    """Expone en el menú lateral las transacciones activas asociadas a la pantalla FACT."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {"menus_facturacion": []}
    return {
        "menus_facturacion": TipoTransaccion.objects.filter(
            activo=True, cod_pantalla__iexact="FACT", modulo__iexact="Facturación"
        ).order_by("nombre", "codigo")
    }
