from decimal import Decimal, InvalidOperation
import secrets
import xml.etree.ElementTree as ET
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.http import HttpResponse, Http404
from django.utils import timezone
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
import qrcode

from apps.clientes.models import Cliente
from apps.empresas.models import Empresa
from apps.productos.models import Producto

from .models import Comprobante, DetalleComprobante, Pago


def decimal_value(value, default="0"):
    try:
        return Decimal(value or default)
    except (InvalidOperation, ValueError):
        return None


def _sub(parent, tag, value):
    node = ET.SubElement(parent, tag)
    node.text = str(value if value is not None else "")
    return node


def _clave_acceso(fecha, tipo, ruc, ambiente, establecimiento, punto, secuencial):
    codigo = f"{secrets.randbelow(100000000):08d}"
    base = fecha.strftime("%d%m%Y") + tipo + ruc + str(ambiente) + establecimiento + punto + f"{secuencial:09d}" + codigo + "1"
    total, factor = 0, 2
    for digito in reversed(base):
        total += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1
    verificador = 11 - (total % 11)
    if verificador == 11:
        verificador = 0
    elif verificador == 10:
        verificador = 1
    return base + str(verificador)


def _generar_xml_factura(comprobante, empresa):
    cliente = comprobante.cliente
    raiz = ET.Element("factura", {"id": "comprobante", "version": "1.1.0"})
    info = ET.SubElement(raiz, "infoTributaria")
    for tag, value in [
        ("ambiente", empresa.ambiente_sri), ("tipoEmision", "1"),
        ("razonSocial", empresa.razon_social), ("nombreComercial", empresa.nombre_comercial),
        ("ruc", empresa.ruc), ("claveAcceso", comprobante.clave_acceso),
        ("codDoc", comprobante.tipo), ("estab", comprobante.establecimiento),
        ("ptoEmi", comprobante.punto_emision), ("secuencial", f"{comprobante.secuencial:09d}"),
        ("dirMatriz", empresa.direccion_matriz or "NO REGISTRADA")
    ]:
        if value != "":
            _sub(info, tag, value)

    info_factura = ET.SubElement(raiz, "infoFactura")
    _sub(info_factura, "fechaEmision", comprobante.fecha_emision.strftime("%d/%m/%Y"))
    _sub(info_factura, "dirEstablecimiento", empresa.direccion_matriz or "NO REGISTRADA")
    _sub(info_factura, "obligadoContabilidad", "SI" if empresa.obligado_contabilidad else "NO")
    _sub(info_factura, "tipoIdentificacionComprador", cliente.tipo_identificacion or "07")
    _sub(info_factura, "razonSocialComprador", cliente.nombres)
    _sub(info_factura, "identificacionComprador", cliente.identificacion)
    _sub(info_factura, "totalSinImpuestos", f"{comprobante.subtotal:.2f}")
    _sub(info_factura, "totalDescuento", f"{comprobante.descuento:.2f}")

    grupos = {}
    for d in comprobante.detalles.select_related("producto").all():
        porcentaje = Decimal(str(d.producto.porcentaje_iva))
        codigo = "0" if porcentaje == 0 else "2" if porcentaje == 12 else "3" if porcentaje == 14 else "5" if porcentaje == 5 else "4"
        grupos.setdefault((codigo, porcentaje), [Decimal("0.00"), Decimal("0.00")])
        grupos[(codigo, porcentaje)][0] += d.subtotal
        grupos[(codigo, porcentaje)][1] += d.iva
    total_impuestos = ET.SubElement(info_factura, "totalConImpuestos")
    for (codigo, porcentaje), (base, valor) in grupos.items():
        imp = ET.SubElement(total_impuestos, "totalImpuesto")
        _sub(imp, "codigo", "2")
        _sub(imp, "codigoPorcentaje", codigo)
        _sub(imp, "baseImponible", f"{base:.2f}")
        _sub(imp, "valor", f"{valor:.2f}")
    _sub(info_factura, "propina", "0.00")
    _sub(info_factura, "importeTotal", f"{comprobante.total:.2f}")
    _sub(info_factura, "moneda", "DOLAR")

    pagos = ET.SubElement(info_factura, "pagos")
    for pago in comprobante.pagos.all():
        item = ET.SubElement(pagos, "pago")
        _sub(item, "formaPago", pago.forma_pago)
        _sub(item, "total", f"{pago.total:.2f}")
        _sub(item, "plazo", pago.plazo)
        _sub(item, "unidadTiempo", pago.unidad_tiempo)

    detalles_xml = ET.SubElement(raiz, "detalles")
    for d in comprobante.detalles.select_related("producto").all():
        item = ET.SubElement(detalles_xml, "detalle")
        _sub(item, "codigoPrincipal", d.codigo)
        _sub(item, "descripcion", d.descripcion)
        _sub(item, "cantidad", f"{d.cantidad:.4f}".rstrip("0").rstrip("."))
        _sub(item, "precioUnitario", f"{d.precio_unitario:.4f}".rstrip("0").rstrip("."))
        _sub(item, "descuento", f"{d.descuento:.2f}")
        _sub(item, "precioTotalSinImpuesto", f"{d.subtotal:.2f}")
        impuestos = ET.SubElement(item, "impuestos")
        imp = ET.SubElement(impuestos, "impuesto")
        porcentaje = Decimal(str(d.producto.porcentaje_iva))
        codigo = "0" if porcentaje == 0 else "2" if porcentaje == 12 else "3" if porcentaje == 14 else "5" if porcentaje == 5 else "4"
        _sub(imp, "codigo", "2")
        _sub(imp, "codigoPorcentaje", codigo)
        _sub(imp, "tarifa", str(porcentaje.normalize()))
        _sub(imp, "baseImponible", f"{d.subtotal:.2f}")
        _sub(imp, "valor", f"{d.iva:.2f}")

    if getattr(cliente, "email", ""):
        adicional = ET.SubElement(raiz, "infoAdicional")
        campo = ET.SubElement(adicional, "campoAdicional", {"nombre": "Email"})
        campo.text = cliente.email
    return ET.tostring(raiz, encoding="unicode")


@login_required
def lista(request):
    return render(request, "facturacion/lista.html", {
        "comprobantes": Comprobante.objects.select_related("cliente").order_by("-fecha_emision", "-id")
    })

@login_required
def consulta_general(request):
    comprobantes = Comprobante.objects.select_related("cliente").order_by("-fecha_emision", "-id")
    return render(request, "facturacion/consulta_general.html", {"comprobantes": comprobantes})


@login_required
def descargar_xml(request, pk):
    comprobante = get_object_or_404(Comprobante, pk=pk)
    if not comprobante.xml_generado:
        raise Http404("Este comprobante todavía no tiene XML generado.")
    nombre = f"factura_{comprobante.establecimiento}-{comprobante.punto_emision}-{comprobante.secuencial:09d}.xml"
    response = HttpResponse(comprobante.xml_generado, content_type="application/xml; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{nombre}"'
    return response


@login_required
def descargar_ride(request, pk):
    comprobante = get_object_or_404(
        Comprobante.objects.select_related("cliente").prefetch_related("detalles__producto", "pagos"),
        pk=pk,
    )
    empresa = Empresa.objects.filter(activo=True).order_by("id").first()
    if not empresa:
        raise Http404("No existe una empresa emisora activa para generar el RIDE.")

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=15*mm, leftMargin=15*mm,
        topMargin=12*mm, bottomMargin=12*mm,
        title=f"RIDE {comprobante.establecimiento}-{comprobante.punto_emision}-{comprobante.secuencial:09d}",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="EmpresaTitle", parent=styles["Title"], fontSize=14, leading=17, alignment=0, textColor=colors.HexColor("#172554")))
    styles.add(ParagraphStyle(name="SmallText", parent=styles["Normal"], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="RightText", parent=styles["Normal"], alignment=TA_RIGHT, fontSize=9))
    story = []
    numero = f"{comprobante.establecimiento}-{comprobante.punto_emision}-{comprobante.secuencial:09d}"
    story.append(Paragraph(empresa.razon_social, styles["EmpresaTitle"]))
    if empresa.nombre_comercial:
        story.append(Paragraph(empresa.nombre_comercial, styles["Normal"]))
    story.append(Paragraph(f"RUC: {empresa.ruc}<br/>Matriz: {empresa.direccion_matriz or 'No registrada'}", styles["SmallText"]))
    story.append(Spacer(1, 5*mm))

    qr_buffer = BytesIO()
    qr_img = qrcode.make(comprobante.clave_acceso or numero)
    qr_img.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr = Image(qr_buffer, width=28*mm, height=28*mm)
    resumen = [
        [Paragraph("<b>COMPROBANTE ELECTRÓNICO</b>", styles["Normal"]), Paragraph("<b>FACTURA</b>", styles["Normal"])],
        [Paragraph(f"<b>No.</b> {numero}<br/><b>Fecha de emisión:</b> {comprobante.fecha_emision.strftime('%d/%m/%Y')}<br/><b>Ambiente:</b> {'Pruebas' if empresa.ambiente_sri == 1 else 'Producción'}<br/><b>Emisión:</b> Normal", styles["SmallText"]),
         Paragraph(f"<b>Clave de acceso:</b><br/>{comprobante.clave_acceso}", styles["SmallText"])],
        [Paragraph(f"<b>Razón social:</b> {empresa.razon_social}<br/><b>RUC:</b> {empresa.ruc}<br/><b>Dirección matriz:</b> {empresa.direccion_matriz or 'No registrada'}", styles["SmallText"]), qr],
    ]
    tabla_resumen = Table(resumen, colWidths=[100*mm, 75*mm])
    tabla_resumen.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.7, colors.HexColor("#94A3B8")),
        ("INNERGRID", (0,0), (-1,-1), 0.4, colors.HexColor("#CBD5E1")),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#EFF6FF")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7),
        ("TOPPADDING", (0,0), (-1,-1), 6), ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(tabla_resumen)
    story.append(Spacer(1, 5*mm))

    comprador = [
        [Paragraph("<b>DATOS DEL CLIENTE</b>", styles["Normal"])],
        [Paragraph(f"<b>Identificación:</b> {comprobante.cliente.identificacion}<br/><b>Razón social / nombres:</b> {comprobante.cliente.nombres}<br/><b>Dirección:</b> {getattr(comprobante.cliente, 'direccion', '') or 'No registrada'}<br/><b>Email:</b> {getattr(comprobante.cliente, 'email', '') or 'No registrado'}", styles["SmallText"])],
    ]
    tabla_cliente = Table(comprador, colWidths=[175*mm])
    tabla_cliente.setStyle(TableStyle([
        ("BOX", (0,0), (-1,-1), 0.7, colors.HexColor("#94A3B8")),
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#EFF6FF")),
        ("LEFTPADDING", (0,0), (-1,-1), 7), ("TOPPADDING", (0,0), (-1,-1), 6),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
    ]))
    story.append(tabla_cliente)
    story.append(Spacer(1, 5*mm))

    filas = [[
        Paragraph("<b>Código</b>", styles["SmallText"]),
        Paragraph("<b>Descripción</b>", styles["SmallText"]),
        Paragraph("<b>Cant.</b>", styles["SmallText"]),
        Paragraph("<b>Precio unit.</b>", styles["SmallText"]),
        Paragraph("<b>Descuento</b>", styles["SmallText"]),
        Paragraph("<b>Total</b>", styles["SmallText"]),
    ]]
    for item in comprobante.detalles.all():
        filas.append([
            Paragraph(str(item.codigo), styles["SmallText"]),
            Paragraph(str(item.descripcion)[:300], styles["SmallText"]),
            f"{item.cantidad.normalize():f}",
            f"$ {item.precio_unitario:.2f}",
            f"$ {item.descuento:.2f}",
            f"$ {item.total:.2f}",
        ])
    tabla_detalles = Table(filas, colWidths=[22*mm, 69*mm, 18*mm, 25*mm, 20*mm, 21*mm], repeatRows=1)
    tabla_detalles.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#DBEAFE")),
        ("GRID", (0,0), (-1,-1), 0.35, colors.HexColor("#CBD5E1")),
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("ALIGN", (2,1), (-1,-1), "RIGHT"),
        ("LEFTPADDING", (0,0), (-1,-1), 4), ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(tabla_detalles)
    story.append(Spacer(1, 4*mm))

    totales = [
        ["Subtotal", f"$ {comprobante.subtotal:.2f}"],
        ["Descuento", f"$ {comprobante.descuento:.2f}"],
        ["IVA", f"$ {comprobante.iva:.2f}"],
        ["VALOR TOTAL", f"$ {comprobante.total:.2f}"],
    ]
    tabla_totales = Table(totales, colWidths=[40*mm, 35*mm], hAlign="RIGHT")
    tabla_totales.setStyle(TableStyle([
        ("ALIGN", (1,0), (1,-1), "RIGHT"),
        ("LINEABOVE", (0,3), (-1,3), 0.8, colors.HexColor("#334155")),
        ("FONTNAME", (0,3), (-1,3), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 9),
        ("TOPPADDING", (0,0), (-1,-1), 4), ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(tabla_totales)
    story.append(Spacer(1, 5*mm))
    story.append(Paragraph(f"<b>Estado en el sistema:</b> {comprobante.get_estado_display()}. Este RIDE es una representación impresa de los datos guardados; no confirma por sí solo la autorización del SRI.", styles["SmallText"]))
    doc.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="RIDE_{numero.replace("-", "_")}.pdf"'
    return response


@login_required
def nuevo(request):
    clientes = Cliente.objects.filter(activo=True).only("id", "identificacion", "nombres").order_by("nombres")
    clientes_data = [{"id": c.id, "identificacion": c.identificacion, "nombres": c.nombres} for c in clientes]
    productos = Producto.objects.filter(activo=True).order_by("nombre")
    productos_data = [{"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "precio": str(p.precio), "iva": str(p.porcentaje_iva)} for p in productos]

    if request.method == "POST":
        cliente_id = request.POST.get("cliente")
        tipo = request.POST.get("tipo", "01")
        establecimiento = request.POST.get("establecimiento", "001").strip()
        punto_emision = request.POST.get("punto_emision", "001").strip()

        try:
            cliente = Cliente.objects.get(pk=cliente_id, activo=True)
        except (Cliente.DoesNotExist, ValueError, TypeError):
            return render(request, "facturacion/nuevo.html", {
                "clientes": clientes, "clientes_data": clientes_data, "productos": productos, "productos_data": productos_data,
                "error": "Selecciona un cliente válido.",
                "form": request.POST,
            })

        if len(establecimiento) != 3 or len(punto_emision) != 3:
            return render(request, "facturacion/nuevo.html", {
                "clientes": clientes, "clientes_data": clientes_data, "productos": productos, "productos_data": productos_data,
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
                "clientes": clientes, "clientes_data": clientes_data, "productos": productos, "productos_data": productos_data,
                "error": "Agrega al menos un producto a la factura.",
                "form": request.POST,
            })

        total = subtotal + iva
        empresa = Empresa.objects.filter(activo=True).order_by("id").first()
        if not empresa:
            return render(request, "facturacion/nuevo.html", {
                "clientes": clientes, "clientes_data": clientes_data, "productos": productos, "productos_data": productos_data,
                "error": "Primero registra y activa una empresa emisora en la pantalla Empresas.",
                "form": request.POST,
            })

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
            comprobante.clave_acceso = _clave_acceso(comprobante.fecha_emision, comprobante.tipo, empresa.ruc, empresa.ambiente_sri, establecimiento, punto_emision, secuencial)
            comprobante.save(update_fields=["clave_acceso", "actualizado"])

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
            comprobante.xml_generado = _generar_xml_factura(comprobante, empresa)
            comprobante.save(update_fields=["xml_generado", "actualizado"])

        return redirect("facturacion:lista")

    return render(request, "facturacion/nuevo.html", {
        "clientes": clientes,
        "clientes_data": clientes_data,
        "productos": productos,
        "productos_data": productos_data,
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
