from decimal import Decimal, InvalidOperation
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.clientes.models import Cliente
from apps.productos.models import Producto

from .models import Comprobante, DetalleComprobante, Pago


def decimal_value(value, default="0"):
    try:
        return Decimal(value or default)
    except (InvalidOperation, ValueError):
        return None


@login_required
def lista(request):
    return render(request, "facturacion/lista.html", {
        "comprobantes": Comprobante.objects.select_related("cliente").order_by("-fecha_emision", "-id")
    })


@login_required
def nuevo(request):
    clientes = Cliente.objects.filter(activo=True).order_by("nombres")
    productos = Producto.objects.filter(activo=True).order_by("nombre")

    if request.method == "POST":
        cliente_id = request.POST.get("cliente")
        tipo = request.POST.get("tipo", "01")
        establecimiento = request.POST.get("establecimiento", "001").strip()
        punto_emision = request.POST.get("punto_emision", "001").strip()

        try:
            cliente = Cliente.objects.get(pk=cliente_id, activo=True)
        except (Cliente.DoesNotExist, ValueError, TypeError):
            return render(request, "facturacion/nuevo.html", {
                "clientes": clientes, "productos": productos,
                "error": "Selecciona un cliente válido.",
                "form": request.POST,
            })

        if len(establecimiento) != 3 or len(punto_emision) != 3:
            return render(request, "facturacion/nuevo.html", {
                "clientes": clientes, "productos": productos,
                "error": "El establecimiento y el punto de emisión deben tener 3 dígitos.",
                "form": request.POST,
            })

        producto_ids = request.POST.getlist("producto_id")
        cantidades = request.POST.getlist("cantidad")

        items = []
        subtotal = Decimal("0")
        iva = Decimal("0")

        for producto_id, cantidad_texto in zip(producto_ids, cantidades):
            if not producto_id:
                continue
            try:
                producto = Producto.objects.get(pk=producto_id, activo=True)
                cantidad = decimal_value(cantidad_texto)
            except (Producto.DoesNotExist, ValueError, TypeError):
                cantidad = None

            if cantidad is None or cantidad <= 0:
                continue

            base = (producto.precio * cantidad).quantize(Decimal("0.01"))
            impuesto = (base * producto.porcentaje_iva / Decimal("100")).quantize(Decimal("0.01"))
            total_linea = base + impuesto

            items.append((producto, cantidad, base, impuesto, total_linea))
            subtotal += base
            iva += impuesto

        if not items:
            return render(request, "facturacion/nuevo.html", {
                "clientes": clientes, "productos": productos,
                "error": "Agrega al menos un producto a la factura.",
                "form": request.POST,
            })

        total = subtotal + iva

        with transaction.atomic():
            ultimo = (
                Comprobante.objects.select_for_update()
                .filter(tipo=tipo, establecimiento=establecimiento, punto_emision=punto_emision)
                .order_by("-secuencial")
                .first()
            )
            secuencial = (ultimo.secuencial + 1) if ultimo else 1

            comprobante = Comprobante.objects.create(
                tipo=tipo,
                fecha_emision=timezone.localdate(),
                establecimiento=establecimiento,
                punto_emision=punto_emision,
                secuencial=secuencial,
                cliente=cliente,
                subtotal=subtotal,
                iva=iva,
                total=total,
                estado="BORRADOR",
            )

            for producto, cantidad, base, impuesto, total_linea in items:
                DetalleComprobante.objects.create(
                    comprobante=comprobante,
                    producto=producto,
                    codigo=producto.codigo,
                    descripcion=producto.nombre,
                    cantidad=cantidad,
                    precio_unitario=producto.precio,
                    subtotal=base,
                    iva=impuesto,
                    total=total_linea,
                )

            Pago.objects.create(
                comprobante=comprobante,
                forma_pago=request.POST.get("forma_pago", "20"),
                total=total,
            )

        return redirect("facturacion:lista")

    return render(request, "facturacion/nuevo.html", {
        "clientes": clientes,
        "productos": productos,
    })


@login_required
def detalle(request, pk):
    comprobante = get_object_or_404(
        Comprobante.objects.select_related("cliente").prefetch_related("detalles__producto", "pagos"),
        pk=pk,
    )
    return render(request, "facturacion/detalle.html", {"comprobante": comprobante})


@login_required
def anular(request, pk):
    comprobante = get_object_or_404(Comprobante, pk=pk)
    if request.method == "POST" and comprobante.estado == "BORRADOR":
        comprobante.estado = "NO_AUTORIZADO"
        comprobante.mensaje_sri = "Documento anulado antes de su envío al SRI."
        comprobante.save(update_fields=["estado", "mensaje_sri", "actualizado"])
    return redirect("facturacion:lista")
