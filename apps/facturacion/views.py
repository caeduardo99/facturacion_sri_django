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
from reportlab.graphics.barcode.code128 import Code128

from apps.clientes.models import Cliente
from apps.empresas.models import Empresa
from apps.productos.models import Producto

from .models import Comprobante, DetalleComprobante, Pago, TipoTransaccion, Oferta, DetalleOferta


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


def _generar_xml_factura(comprobante, empresa, ambiente_sri=None):
    cliente = comprobante.cliente
    raiz = ET.Element("factura", {"id": "comprobante", "version": "1.1.0"})
    info = ET.SubElement(raiz, "infoTributaria")
    for tag, value in [
        ("ambiente", ambiente_sri or empresa.ambiente_sri), ("tipoEmision", "1"),
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
def ofertas(request):
    clientes = Cliente.objects.filter(activo=True).order_by("nombres")
    productos = Producto.objects.filter(activo=True).order_by("nombre")
    if request.method == "POST":
        cliente_id = request.POST.get("cliente")
        try:
            cliente = Cliente.objects.get(pk=cliente_id, activo=True)
        except (Cliente.DoesNotExist, ValueError, TypeError):
            return render(request, "facturacion/ofertas.html", {"clientes": clientes, "productos_data": [{"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "precio": str(p.precio), "iva": str(p.porcentaje_iva)} for p in productos], "error": "Selecciona un cliente válido."})
        ids = request.POST.getlist("producto_id")
        cantidades = request.POST.getlist("cantidad")
        items = []
        subtotal = Decimal("0.00")
        iva_total = Decimal("0.00")
        for pid, cantidad_txt in zip(ids, cantidades):
            try:
                producto = Producto.objects.get(pk=pid, activo=True)
                cantidad = decimal_value(cantidad_txt)
            except (Producto.DoesNotExist, ValueError, TypeError):
                cantidad = None
            if cantidad is None or cantidad <= 0:
                continue
            base = (producto.precio * cantidad).quantize(Decimal("0.01"))
            impuesto = (base * producto.porcentaje_iva / Decimal("100")).quantize(Decimal("0.01"))
            items.append((producto, cantidad, base, impuesto, base + impuesto))
            subtotal += base
            iva_total += impuesto
        if not items:
            return render(request, "facturacion/ofertas.html", {"clientes": clientes, "productos_data": [{"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "precio": str(p.precio), "iva": str(p.porcentaje_iva)} for p in productos], "error": "Agrega al menos un producto a la oferta."})
        with transaction.atomic():
            oferta = Oferta.objects.create(cliente=cliente, subtotal=subtotal, iva=iva_total, total=subtotal + iva_total)
            oferta.estado = "APROBADA"
            oferta.save(update_fields=["estado", "actualizado"])
            for producto, cantidad, base, impuesto, total_linea in items:
                DetalleOferta.objects.create(oferta=oferta, producto=producto, codigo=producto.codigo, descripcion=producto.nombre, cantidad=cantidad, precio_unitario=producto.precio, subtotal=base, iva=impuesto, total=total_linea)
        return redirect("facturacion:ofertas")
    lista_ofertas = Oferta.objects.select_related("cliente").prefetch_related("detalles").all()
    return render(request, "facturacion/ofertas.html", {"clientes": clientes, "productos_data": [{"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "precio": str(p.precio), "iva": str(p.porcentaje_iva)} for p in productos], "ofertas": lista_ofertas})


@login_required
def oferta_detalle_json(request, pk):
    oferta = get_object_or_404(Oferta.objects.select_related("cliente").prefetch_related("detalles__producto"), pk=pk, estado="APROBADA")
    return HttpResponse(__import__("json").dumps({
        "id": oferta.id, "numero": oferta.numero, "cliente_id": oferta.cliente_id,
        "cliente": oferta.cliente.nombres, "identificacion": oferta.cliente.identificacion,
        "items": [{"producto_id": d.producto_id, "cantidad": str(d.cantidad)} for d in oferta.detalles.all()]
    }), content_type="application/json")


@login_required
def configuracion_menus(request):
    menus = TipoTransaccion.objects.all().order_by("modulo", "nombre")
    return render(request, "facturacion/configuracion_menus.html", {"menus": menus})


@login_required
def catalogo_transacciones(request):
    # Asegurar que el módulo de Ofertas también esté registrado en el catálogo.
    TipoTransaccion.objects.get_or_create(
        codigo="OF",
        defaults={
            "nombre": "Ofertas",
            "descripcion": "Registro y gestión de ofertas comerciales",
            "cod_pantalla": "OF",
            "modulo": "Ofertas",
            "documento_electronico": False,
            "activo": True,
        },
    )
    q = request.GET.get("q", "").strip()
    transacciones = TipoTransaccion.objects.all()
    if q:
        from django.db.models import Q
        transacciones = transacciones.filter(Q(codigo__icontains=q) | Q(nombre__icontains=q) | Q(modulo__icontains=q))
    return render(request, "facturacion/catalogo_transacciones.html", {
        "transacciones": transacciones,
        "q": q,
    })


@login_required
def transaccion_form(request, pk=None):
    transaccion = get_object_or_404(TipoTransaccion, pk=pk) if pk else None
    if request.method == "POST":
        codigo = request.POST.get("codigo", "").strip().upper()
        nombre = request.POST.get("nombre", "").strip()
        if not codigo or not nombre:
            return render(request, "facturacion/transaccion_form.html", {
                "transaccion": transaccion, "error": "El código y el nombre son obligatorios.", "form": request.POST, "doc_codes": [("01", "Factura"), ("03", "Liquidación de compra"), ("04", "Nota de crédito"), ("05", "Nota de débito"), ("06", "Guía de remisión"), ("07", "Retención")],
            })
        duplicado = TipoTransaccion.objects.filter(codigo__iexact=codigo)
        if transaccion:
            duplicado = duplicado.exclude(pk=transaccion.pk)
        if duplicado.exists():
            return render(request, "facturacion/transaccion_form.html", {
                "transaccion": transaccion, "error": "Ya existe una transacción con ese código.", "form": request.POST, "doc_codes": [("01", "Factura"), ("03", "Liquidación de compra"), ("04", "Nota de crédito"), ("05", "Nota de débito"), ("06", "Guía de remisión"), ("07", "Retención")],
            })
        if transaccion is None:
            transaccion = TipoTransaccion()
        transaccion.codigo = codigo
        transaccion.nombre = nombre
        transaccion.descripcion = request.POST.get("descripcion", "").strip()
        transaccion.cod_pantalla = request.POST.get("cod_pantalla", "").strip()
        transaccion.modulo = request.POST.get("modulo", "Facturación").strip() or "Facturación"
        transaccion.transaccion_siguiente = int(request.POST.get("transaccion_siguiente") or 1)
        transaccion.establecimiento = request.POST.get("establecimiento", "001").strip()
        transaccion.punto_emision = request.POST.get("punto_emision", "001").strip()
        if len(transaccion.establecimiento) != 3 or not transaccion.establecimiento.isdigit() or len(transaccion.punto_emision) != 3 or not transaccion.punto_emision.isdigit():
            return render(request, "facturacion/transaccion_form.html", {
                "transaccion": transaccion, "error": "El establecimiento y el punto de emisión deben ser códigos numéricos de 3 dígitos.", "form": request.POST, "doc_codes": [("01", "Factura"), ("03", "Liquidación de compra"), ("04", "Nota de crédito"), ("05", "Nota de débito"), ("06", "Guía de remisión"), ("07", "Retención")],
            })
        transaccion.sucursal = request.POST.get("sucursal", "").strip()
        transaccion.libreria_impresion = request.POST.get("libreria_impresion", "").strip()
        transaccion.libreria_ride = request.POST.get("libreria_ride", "").strip()
        transaccion.documento_electronico = request.POST.get("documento_electronico") == "on"
        transaccion.codigo_documento_sri = request.POST.get("codigo_documento_sri", "").strip()
        transaccion.ambiente_sri = int(request.POST.get("ambiente_sri") or 1)
        transaccion.utiliza_formato_estandar_xml = request.POST.get("utiliza_formato_estandar_xml") == "on"
        transaccion.generacion_bloque_xml = request.POST.get("generacion_bloque_xml") == "on"
        transaccion.seis_decimales = request.POST.get("seis_decimales") == "on"
        transaccion.importacion_requerida = request.POST.get("importacion_requerida") == "on"
        transaccion.activo = request.POST.get("activo") == "on"
        transaccion.save()
        return redirect("facturacion:catalogo_transacciones")
    if transaccion:
        ultimo_comprobante = Comprobante.objects.filter(
            codigo_transaccion__iexact=transaccion.codigo,
            establecimiento=transaccion.establecimiento,
            punto_emision=transaccion.punto_emision,
        ).order_by("-secuencial").first()
        if ultimo_comprobante:
            # Mostrar el siguiente secuencial real aunque la factura se haya creado antes
            # de que se actualizara automáticamente el contador de la configuración.
            transaccion.transaccion_siguiente = max(
                transaccion.transaccion_siguiente, ultimo_comprobante.secuencial + 1
            )
    return render(request, "facturacion/transaccion_form.html", {"transaccion": transaccion, "doc_codes": [("01", "Factura"), ("03", "Liquidación de compra"), ("04", "Nota de crédito"), ("05", "Nota de débito"), ("06", "Guía de remisión"), ("07", "Retención")]})


@login_required
def transaccion_eliminar(request, pk):
    transaccion = get_object_or_404(TipoTransaccion, pk=pk)
    if request.method == "POST":
        transaccion.activo = False
        transaccion.save(update_fields=["activo", "actualizado"])
    return redirect("facturacion:catalogo_transacciones")


@login_required
def lista(request):
    return render(request, "facturacion/lista.html", {
        "comprobantes": Comprobante.objects.select_related("cliente").order_by("-fecha_emision", "-id")
    })

@login_required
def cambiar_estado_transaccion(request, pk):
    comprobante = get_object_or_404(Comprobante, pk=pk)
    if request.method == "POST":
        nuevo_estado = request.POST.get("estado_transaccion", "").strip()
        validos = {codigo for codigo, etiqueta in Comprobante.ESTADOS_TRANSACCION}
        if nuevo_estado in validos:
            comprobante.estado_transaccion = nuevo_estado
            comprobante.save(update_fields=["estado_transaccion", "actualizado"])
    return redirect("facturacion:consulta_general")


@login_required
def consulta_general(request):
    comprobantes = Comprobante.objects.select_related("cliente").all()
    ofertas = Oferta.objects.select_related("cliente").all()
    desde = request.GET.get("desde", "").strip()
    hasta = request.GET.get("hasta", "").strip()
    tipo = request.GET.get("tipo", "").strip()
    numero_desde = request.GET.get("numero_desde", "").strip()
    numero_hasta = request.GET.get("numero_hasta", "").strip()
    estado_sri = request.GET.get("estado_sri", "").strip()
    estado_transaccion = request.GET.get("estado_transaccion", "").strip()
    buscar = request.GET.get("buscar", "").strip()
    if desde:
        comprobantes = comprobantes.filter(fecha_emision__gte=desde)
        ofertas = ofertas.filter(fecha__gte=desde)
    if hasta:
        comprobantes = comprobantes.filter(fecha_emision__lte=hasta)
        ofertas = ofertas.filter(fecha__lte=hasta)
    if tipo:
        comprobantes = comprobantes.filter(tipo=tipo)
        ofertas = Oferta.objects.none()
    if numero_desde.isdigit():
        comprobantes = comprobantes.filter(secuencial__gte=int(numero_desde))
        ofertas = ofertas.filter(id__gte=int(numero_desde))
    if numero_hasta.isdigit():
        comprobantes = comprobantes.filter(secuencial__lte=int(numero_hasta))
        ofertas = ofertas.filter(id__lte=int(numero_hasta))
    if estado_sri:
        comprobantes = comprobantes.filter(estado=estado_sri)
        ofertas = Oferta.objects.none()
    if estado_transaccion:
        comprobantes = comprobantes.filter(estado_transaccion=estado_transaccion)
        ofertas = ofertas.filter(estado=estado_transaccion)
    if buscar:
        from django.db.models import Q
        comprobantes = comprobantes.filter(Q(cliente__identificacion__icontains=buscar) | Q(cliente__nombres__icontains=buscar) | Q(clave_acceso__icontains=buscar) | Q(secuencial__icontains=buscar))
        ofertas = ofertas.filter(Q(cliente__identificacion__icontains=buscar) | Q(cliente__nombres__icontains=buscar) | Q(numero__icontains=buscar) | Q(id__icontains=buscar))
    comprobantes = comprobantes.order_by("-fecha_emision", "-id")
    ofertas = ofertas.order_by("-fecha", "-id")
    return render(request, "facturacion/consulta_general.html", {
        "comprobantes": comprobantes, "ofertas": ofertas, "desde": desde, "hasta": hasta, "tipo": tipo,
        "numero_desde": numero_desde, "numero_hasta": numero_hasta, "estado_sri": estado_sri,
        "estado_transaccion": estado_transaccion, "buscar": buscar,
        "tipos": Comprobante.TIPOS, "estados_sri": Comprobante.ESTADOS,
        "estados_transaccion": Comprobante.ESTADOS_TRANSACCION,
    })

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
    # El XML conserva el ambiente utilizado al crear el comprobante. Así el RIDE
    # no depende de que la configuración FE siga siendo la seleccionada por defecto.
    ambiente_ride = empresa.ambiente_sri
    if comprobante.xml_generado:
        try:
            raiz_xml = ET.fromstring(comprobante.xml_generado)
            nodo_ambiente = raiz_xml.find("./infoTributaria/ambiente")
            if nodo_ambiente is not None and nodo_ambiente.text:
                ambiente_ride = int(nodo_ambiente.text)
        except (ET.ParseError, TypeError, ValueError):
            pass

    buffer = BytesIO()
    numero = f"{comprobante.establecimiento}-{comprobante.punto_emision}-{comprobante.secuencial:09d}"
    clave = comprobante.clave_acceso or ""
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=10*mm, leftMargin=10*mm,
        topMargin=8*mm, bottomMargin=10*mm, title=f"RIDE {numero}",
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="RideSmall", parent=styles["Normal"], fontSize=6.8, leading=8.2, spaceAfter=0))
    styles.add(ParagraphStyle(name="RideTiny", parent=styles["Normal"], fontSize=5.8, leading=7, spaceAfter=0))
    styles.add(ParagraphStyle(name="RideSection", parent=styles["Normal"], fontSize=7.2, leading=8.5, spaceAfter=0))
    styles.add(ParagraphStyle(name="RideRight", parent=styles["RideSmall"], alignment=TA_RIGHT))
    styles.add(ParagraphStyle(name="RideBold", parent=styles["RideSmall"], fontName="Helvetica-Bold"))
    story = []
    border = colors.black
    pad = 4

    def P(text, style="RideSmall"):
        return Paragraph(str(text), styles[style])

    # Encabezado: datos del emisor a la izquierda y bloque tributario a la derecha,
    # siguiendo la distribución del RIDE de referencia adjuntado.
    emisor = [
        [P(f"<b>{empresa.razon_social}</b>", "RideSection")],
        [P(empresa.nombre_comercial or "", "RideSmall")],
        [P(f"<b>Dirección Matriz:</b> {empresa.direccion_matriz or ''}")],
        [P(f"<b>Dirección Sucursal:</b> {empresa.direccion_matriz or ''}")],
        [P(f"<b>OBLIGADO A LLEVAR CONTABILIDAD</b> &nbsp;&nbsp;&nbsp; {'SI' if empresa.obligado_contabilidad else 'NO'}")],
    ]
    tabla_emisor = Table(emisor, colWidths=[83*mm], rowHeights=[None, None, 15*mm, 15*mm, 12*mm])
    tabla_emisor.setStyle(TableStyle([
        ("BOX",(0,0),(-1,-1),0.7,border),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),pad),("RIGHTPADDING",(0,0),(-1,-1),pad),
        ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
    ]))

    barcode_cell = P("CLAVE DE ACCESO", "RideBold")
    if clave:
        barcode = Code128(clave, barHeight=8*mm, barWidth=0.12*mm, humanReadable=True)
        barcode_cell = [barcode_cell, Spacer(1, 2*mm), barcode]

    datos_tributarios = [
        [P(f"<b>R.U.C.:</b> {empresa.ruc}", "RideSection")],
        [P("<b>FACTURA</b>", "RideSection")],
        [P(f"<b>No.</b> {numero}")],
        [P("<b>NÚMERO DE AUTORIZACIÓN</b>")],
        [P(clave)],
        [P("<b>FECHA Y HORA DE AUTORIZACIÓN:</b> PENDIENTE DE AUTORIZACIÓN")],
        [P(f"<b>AMBIENTE:</b> {'PRUEBAS' if ambiente_ride == 1 else 'PRODUCCIÓN'}")],
        [P("<b>EMISIÓN:</b> NORMAL")],
        [barcode_cell],
    ]
    tabla_tributaria = Table(datos_tributarios, colWidths=[87*mm])
    tabla_tributaria.setStyle(TableStyle([
        ("BOX",(0,0),(-1,-1),0.7,border),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),pad),("RIGHTPADDING",(0,0),(-1,-1),pad),
        ("TOPPADDING",(0,0),(-1,-1),3),("BOTTOMPADDING",(0,0),(-1,-1),3),
    ]))
    cabecera = Table([[tabla_emisor, tabla_tributaria]], colWidths=[86*mm, 89*mm])
    cabecera.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),2)]))
    story.append(cabecera)
    story.append(Spacer(1, 4*mm))

    comprador = [
        [P("<b>Razón Social / Nombres y Apellidos:</b>"), P(comprobante.cliente.nombres),
         P("<b>Placa / Matrícula:</b>"), P("")],
        [P("<b>Identificación</b>"), P(comprobante.cliente.identificacion),
         P("<b>Guía</b>"), P("")],
        [P("<b>Fecha</b>"), P(comprobante.fecha_emision.strftime("%d/%m/%Y")),
         P("<b>Dirección:</b>"), P(getattr(comprobante.cliente, "direccion", "") or "")],
    ]
    tabla_comprador = Table(comprador, colWidths=[35*mm, 58*mm, 32*mm, 50*mm])
    tabla_comprador.setStyle(TableStyle([
        ("BOX",(0,0),(-1,-1),0.7,border),("INNERGRID",(0,0),(-1,-1),0.35,colors.HexColor("#777777")),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),pad),
        ("RIGHTPADDING",(0,0),(-1,-1),pad),("TOPPADDING",(0,0),(-1,-1),5),
        ("BOTTOMPADDING",(0,0),(-1,-1),5),
    ]))
    story.append(tabla_comprador)
    story.append(Spacer(1, 3*mm))

    encabezados = [P("<b>Cod.<br/>Principal</b>","RideTiny"), P("<b>Cod.<br/>Auxiliar</b>","RideTiny"),
        P("<b>Cantidad</b>","RideTiny"), P("<b>Descripción</b>","RideTiny"),
        P("<b>Detalle Adicional</b>","RideTiny"), P("<b>Precio Unitario</b>","RideTiny"),
        P("<b>Subsidio</b>","RideTiny"), P("<b>Precio sin Subsidio</b>","RideTiny"),
        P("<b>Descuento</b>","RideTiny"), P("<b>Precio Total</b>","RideTiny")]
    filas = [encabezados]
    for item in comprobante.detalles.all():
        filas.append([
            P(item.codigo,"RideTiny"), P("","RideTiny"), P(f"{item.cantidad:.2f}","RideTiny"),
            P(item.descripcion,"RideTiny"), P("","RideTiny"), P(f"{item.precio_unitario:.2f}","RideTiny"),
            P("0.00","RideTiny"), P(f"{item.precio_unitario:.2f}","RideTiny"),
            P(f"{item.descuento:.2f}","RideTiny"), P(f"{item.total:.2f}","RideTiny")
        ])
    tabla_detalles = Table(filas, colWidths=[14*mm, 12*mm, 14*mm, 34*mm, 20*mm, 16*mm, 11*mm, 17*mm, 14*mm, 23*mm], repeatRows=1)
    tabla_detalles.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.45,border),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("ALIGN",(0,0),(-1,-1),"CENTER"),("LEFTPADDING",(0,0),(-1,-1),2),
        ("RIGHTPADDING",(0,0),(-1,-1),2),("TOPPADDING",(0,0),(-1,-1),3),
        ("BOTTOMPADDING",(0,0),(-1,-1),3),("BACKGROUND",(0,0),(-1,0),colors.HexColor("#F2F2F2")),
    ]))
    story.append(tabla_detalles)
    story.append(Spacer(1, 3*mm))

    adicionales = []
    if getattr(comprobante.cliente, "email", ""):
        adicionales.append([P("<b>Email:</b>"), P(comprobante.cliente.email)])
    if not adicionales:
        adicionales = [[P("<b>Información Adicional</b>"), P("")]]
    tabla_adicional = Table([[P("<b>Información Adicional</b>"), P("")]] + adicionales, colWidths=[32*mm, 55*mm])
    tabla_adicional.setStyle(TableStyle([
        ("BOX",(0,0),(-1,-1),0.5,border),("INNERGRID",(0,0),(-1,-1),0.35,border),
        ("SPAN",(0,0),(-1,0)),("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    pagos_filas = [[P("<b>Forma de pago</b>"), P("<b>Valor</b>")]]
    for pago in comprobante.pagos.all():
        pagos_filas.append([P(dict(Pago.FORMAS).get(pago.forma_pago, pago.forma_pago),"RideTiny"), P(f"$ {pago.total:.2f}","RideTiny")])
    if len(pagos_filas) == 1:
        pagos_filas.append([P("No registrado"), P(f"$ {comprobante.total:.2f}")])
    tabla_pagos = Table(pagos_filas, colWidths=[65*mm, 22*mm])
    tabla_pagos.setStyle(TableStyle([("GRID",(0,0),(-1,-1),0.5,border),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),3),("RIGHTPADDING",(0,0),(-1,-1),3),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4)]))

    base_iva = sum((d.subtotal for d in comprobante.detalles.all() if Decimal(str(d.producto.porcentaje_iva)) > 0), Decimal("0.00"))
    base_cero = sum((d.subtotal for d in comprobante.detalles.all() if Decimal(str(d.producto.porcentaje_iva)) == 0), Decimal("0.00"))
    iva_porcentaje = "15%" if comprobante.iva else "0%"
    resumen = [
        [P("SUBTOTAL 15%","RideTiny"), P(f"{base_iva:.2f}","RideTiny")],
        [P("SUBTOTAL 0%","RideTiny"), P(f"{base_cero:.2f}","RideTiny")],
        [P("SUBTOTAL NO OBJETO DE IVA","RideTiny"), P("0.00","RideTiny")],
        [P("SUBTOTAL EXENTO DE IVA","RideTiny"), P("0.00","RideTiny")],
        [P("SUBTOTAL SIN IMPUESTOS","RideTiny"), P(f"{comprobante.subtotal:.2f}","RideTiny")],
        [P("TOTAL DESCUENTO","RideTiny"), P(f"{comprobante.descuento:.2f}","RideTiny")],
        [P("ICE","RideTiny"), P("0.00","RideTiny")],
        [P(f"IVA {iva_porcentaje}","RideTiny"), P(f"{comprobante.iva:.2f}","RideTiny")],
        [P("IRBPNR","RideTiny"), P("0.00","RideTiny")],
        [P("PROPINA","RideTiny"), P("0.00","RideTiny")],
        [P("VALOR TOTAL","RideTiny"), P(f"{comprobante.total:.2f}","RideTiny")],
        [P("VALOR TOTAL SIN SUBSIDIO","RideTiny"), P(f"{comprobante.total:.2f}","RideTiny")],
        [P("AHORRO POR SUBSIDIO (incluye IVA cuando corresponda)","RideTiny"), P("0.00","RideTiny")],
    ]
    tabla_resumen = Table(resumen, colWidths=[57*mm, 24*mm])
    tabla_resumen.setStyle(TableStyle([
        ("GRID",(0,0),(-1,-1),0.45,border),("ALIGN",(1,0),(1,-1),"RIGHT"),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),("LEFTPADDING",(0,0),(-1,-1),3),
        ("RIGHTPADDING",(0,0),(-1,-1),3),("TOPPADDING",(0,0),(-1,-1),4),
        ("BOTTOMPADDING",(0,0),(-1,-1),4),("FONTNAME",(0,10),(-1,10),"Helvetica-Bold"),
    ]))
    parte_inferior = Table([[tabla_adicional, tabla_resumen],[tabla_pagos, ""]], colWidths=[90*mm, 85*mm])
    parte_inferior.setStyle(TableStyle([
        ("VALIGN",(0,0),(-1,-1),"TOP"),("SPAN",(1,0),(1,1)),
        ("LEFTPADDING",(0,0),(-1,-1),0),("RIGHTPADDING",(0,0),(-1,-1),2),
        ("TOPPADDING",(0,0),(-1,-1),0),("BOTTOMPADDING",(0,0),(-1,-1),2),
    ]))
    story.append(parte_inferior)
    doc.build(story)
    response = HttpResponse(buffer.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="RIDE_{numero.replace("-", "_")}.pdf"'
    return response


@login_required
def nuevo(request):
    # Cada entrada del menú FACT envía su propio parámetro (por ejemplo FE o FEZ).
    codigo_transaccion = (
        request.POST.get("codigo_transaccion")
        or request.GET.get("transaccion")
        or "FE"
    ).strip()
    configuracion_fe = TipoTransaccion.objects.filter(
        codigo__iexact=codigo_transaccion,
        activo=True,
        cod_pantalla__iexact="FACT",
        modulo__iexact="Facturación",
    ).first()
    clientes = Cliente.objects.filter(activo=True).only("id", "identificacion", "nombres").order_by("nombres")
    clientes_data = [{"id": c.id, "identificacion": c.identificacion, "nombres": c.nombres} for c in clientes]
    productos = Producto.objects.filter(activo=True).order_by("nombre")
    productos_data = [{"id": p.id, "codigo": p.codigo, "nombre": p.nombre, "precio": str(p.precio), "iva": str(p.porcentaje_iva)} for p in productos]

    if request.method == "POST":
        if not configuracion_fe:
            return render(request, "facturacion/nuevo.html", {
                "clientes": clientes, "clientes_data": clientes_data, "productos": productos, "productos_data": productos_data,
                "error": f"No existe una transacción activa con código {codigo_transaccion} asociada a la pantalla FACT.",
                "form": request.POST,
                "configuracion_fe": configuracion_fe,
                "codigo_transaccion": codigo_transaccion,
            })
        oferta_importada = None
        oferta_id = request.POST.get("oferta_id", "").strip()
        if oferta_id:
            oferta_importada = get_object_or_404(Oferta, pk=oferta_id, estado="APROBADA")
        cliente_id = oferta_importada.cliente_id if oferta_importada else request.POST.get("cliente")
        tipo = configuracion_fe.codigo_documento_sri or "01"
        ambiente_sri = configuracion_fe.ambiente_sri or 1
        # La numeración se toma de la configuración guardada para este código de transacción.
        establecimiento = configuracion_fe.establecimiento
        punto_emision = configuracion_fe.punto_emision

        try:
            cliente = Cliente.objects.get(pk=cliente_id, activo=True)
        except (Cliente.DoesNotExist, ValueError, TypeError):
            return render(request, "facturacion/nuevo.html", {
                "clientes": clientes, "clientes_data": clientes_data, "productos": productos, "productos_data": productos_data,
                "error": "Selecciona un cliente válido.",
                "form": request.POST,
                "configuracion_fe": configuracion_fe,
                "codigo_transaccion": codigo_transaccion,
            })

        if len(establecimiento) != 3 or len(punto_emision) != 3:
            return render(request, "facturacion/nuevo.html", {
                "clientes": clientes, "clientes_data": clientes_data, "productos": productos, "productos_data": productos_data,
                "error": "El establecimiento y el punto de emisión deben tener 3 dígitos.",
                "form": request.POST,
                "configuracion_fe": configuracion_fe,
                "codigo_transaccion": codigo_transaccion,
            })

        items = []
        subtotal = Decimal("0")
        iva = Decimal("0")
        if oferta_importada:
            for detalle_oferta in oferta_importada.detalles.select_related("producto").all():
                producto = detalle_oferta.producto
                cantidad = detalle_oferta.cantidad
                base = detalle_oferta.subtotal
                impuesto = detalle_oferta.iva
                total_linea = detalle_oferta.total
                items.append((producto, cantidad, base, impuesto, total_linea))
                subtotal += base
                iva += impuesto
        else:
            producto_ids = request.POST.getlist("producto_id")
            cantidades = request.POST.getlist("cantidad")
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
                "configuracion_fe": configuracion_fe,
                "codigo_transaccion": codigo_transaccion,
            })

        total = subtotal + iva
        empresa = Empresa.objects.filter(activo=True).order_by("id").first()
        if not empresa:
            return render(request, "facturacion/nuevo.html", {
                "clientes": clientes, "clientes_data": clientes_data, "productos": productos, "productos_data": productos_data,
                "error": "Primero registra y activa una empresa emisora en la pantalla Empresas.",
                "form": request.POST,
                "configuracion_fe": configuracion_fe,
                "codigo_transaccion": codigo_transaccion,
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
                codigo_transaccion=configuracion_fe.codigo,
                oferta=oferta_importada,
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
            comprobante.clave_acceso = _clave_acceso(comprobante.fecha_emision, comprobante.tipo, empresa.ruc, ambiente_sri, establecimiento, punto_emision, secuencial)
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
            comprobante.xml_generado = _generar_xml_factura(comprobante, empresa, ambiente_sri=ambiente_sri)
            comprobante.save(update_fields=["xml_generado", "actualizado"])

            # Mantener visible el siguiente secuencial en la configuración de la transacción.
            configuracion_fe.transaccion_siguiente = secuencial + 1
            configuracion_fe.save(update_fields=["transaccion_siguiente", "actualizado"])
            if oferta_importada:
                oferta_importada.estado = "FACTURADA"
                oferta_importada.save(update_fields=["estado", "actualizado"])

        return redirect("facturacion:lista")

    ofertas_disponibles = Oferta.objects.none()
    filtro_fecha_desde = request.GET.get("fecha_desde", "").strip()
    filtro_fecha_hasta = request.GET.get("fecha_hasta", "").strip()
    filtro_cliente = request.GET.get("cliente_oferta", "").strip()
    if configuracion_fe and configuracion_fe.importacion_requerida:
        ofertas_disponibles = Oferta.objects.filter(estado="APROBADA").select_related("cliente").order_by("-fecha", "-id")
        if filtro_fecha_desde:
            ofertas_disponibles = ofertas_disponibles.filter(fecha__gte=filtro_fecha_desde)
        if filtro_fecha_hasta:
            ofertas_disponibles = ofertas_disponibles.filter(fecha__lte=filtro_fecha_hasta)
        if filtro_cliente:
            ofertas_disponibles = ofertas_disponibles.filter(cliente_id=filtro_cliente)
    return render(request, "facturacion/nuevo.html", {
        "clientes": clientes,
        "clientes_data": clientes_data,
        "productos": productos,
        "productos_data": productos_data,
        "configuracion_fe": configuracion_fe,
        "codigo_transaccion": codigo_transaccion,
        "ofertas_disponibles": ofertas_disponibles,
        "clientes_filtro_oferta": clientes,
        "filtro_fecha_desde": filtro_fecha_desde,
        "filtro_fecha_hasta": filtro_fecha_hasta,
        "filtro_cliente_oferta": filtro_cliente,
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
    if request.method == "POST" and comprobante.estado_transaccion != "ANULADO":
        comprobante.estado_transaccion = "ANULADO"
        if comprobante.estado == "BORRADOR":
            comprobante.mensaje_sri = "Transacción anulada antes de su envío al SRI."
            comprobante.save(update_fields=["estado_transaccion", "mensaje_sri", "actualizado"])
        else:
            comprobante.save(update_fields=["estado_transaccion", "actualizado"])
    return redirect("facturacion:lista")
