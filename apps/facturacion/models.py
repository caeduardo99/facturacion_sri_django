from decimal import Decimal
from django.db import models
class Comprobante(models.Model):
    ESTADOS=[('BORRADOR','Borrador'),('FIRMADO','Firmado'),('RECIBIDA','Recibida'),('AUTORIZADO','Autorizado'),('NO_AUTORIZADO','No autorizado')]
    ESTADOS_TRANSACCION=[('PENDIENTE','Pendiente'),('APROBADO','Aprobado'),('DESPACHADO','Despachado'),('SEMI_DESPACHADO','Semi despachado'),('ANULADO','Anulado')]
    TIPOS=[('01','Factura'),('03','Liquidación de compra'),('04','Nota de crédito'),('05','Nota de débito'),('06','Guía de remisión'),('07','Retención')]
    tipo=models.CharField(max_length=2,choices=TIPOS,default='01'); codigo_transaccion=models.CharField(max_length=10,default='FE'); fecha_emision=models.DateField(); establecimiento=models.CharField(max_length=3,default='001'); punto_emision=models.CharField(max_length=3,default='001'); secuencial=models.PositiveIntegerField(); clave_acceso=models.CharField(max_length=49,unique=True,blank=True); estado=models.CharField(max_length=20,choices=ESTADOS,default='BORRADOR'); estado_transaccion=models.CharField(max_length=20,choices=ESTADOS_TRANSACCION,default='PENDIENTE'); cliente=models.ForeignKey('clientes.Cliente',on_delete=models.PROTECT,related_name='comprobantes'); subtotal=models.DecimalField(max_digits=14,decimal_places=2,default=Decimal('0')); descuento=models.DecimalField(max_digits=14,decimal_places=2,default=Decimal('0')); iva=models.DecimalField(max_digits=14,decimal_places=2,default=Decimal('0')); total=models.DecimalField(max_digits=14,decimal_places=2,default=Decimal('0')); xml_generado=models.TextField(blank=True); xml_firmado=models.TextField(blank=True); xml_autorizado=models.TextField(blank=True); numero_autorizacion=models.CharField(max_length=49,blank=True); mensaje_sri=models.TextField(blank=True); creado=models.DateTimeField(auto_now_add=True); actualizado=models.DateTimeField(auto_now=True)
    class Meta: constraints=[models.UniqueConstraint(fields=['tipo','establecimiento','punto_emision','secuencial'],name='uq_comprobante_numero')]
class DetalleComprobante(models.Model):
    comprobante=models.ForeignKey(Comprobante,on_delete=models.CASCADE,related_name='detalles'); producto=models.ForeignKey('productos.Producto',on_delete=models.PROTECT); codigo=models.CharField(max_length=50); descripcion=models.CharField(max_length=300); cantidad=models.DecimalField(max_digits=14,decimal_places=4); precio_unitario=models.DecimalField(max_digits=14,decimal_places=4); descuento=models.DecimalField(max_digits=14,decimal_places=2,default=Decimal('0')); subtotal=models.DecimalField(max_digits=14,decimal_places=2,default=Decimal('0')); iva=models.DecimalField(max_digits=14,decimal_places=2,default=Decimal('0')); total=models.DecimalField(max_digits=14,decimal_places=2,default=Decimal('0'))
class Pago(models.Model):
    FORMAS=[('01','Sin utilización del sistema financiero'),('16','Tarjeta de débito'),('19','Tarjeta de crédito'),('20','Otros con utilización del sistema financiero')]
    comprobante=models.ForeignKey(Comprobante,on_delete=models.CASCADE,related_name='pagos'); forma_pago=models.CharField(max_length=2,choices=FORMAS,default='20'); total=models.DecimalField(max_digits=14,decimal_places=2); plazo=models.PositiveIntegerField(default=0); unidad_tiempo=models.CharField(max_length=20,default='dias')


class TipoTransaccion(models.Model):
    AMBIENTES = [(1, "Pruebas"), (2, "Producción")]
    codigo = models.CharField(max_length=10, unique=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=250, blank=True)
    cod_pantalla = models.CharField(max_length=30, blank=True)
    modulo = models.CharField(max_length=80, default="Facturación")
    transaccion_siguiente = models.PositiveIntegerField(default=1)
    sucursal = models.CharField(max_length=20, blank=True, default="CUENCA")
    libreria_impresion = models.CharField(max_length=100, blank=True, default="gnprintG")
    libreria_ride = models.CharField(max_length=100, blank=True, default="gnprintg")
    documento_electronico = models.BooleanField(default=False)
    codigo_documento_sri = models.CharField(max_length=2, blank=True, help_text="Código SRI: 01 factura, 04 nota de crédito, 05 nota de débito, etc.")
    ambiente_sri = models.PositiveSmallIntegerField(choices=AMBIENTES, default=1)
    utiliza_formato_estandar_xml = models.BooleanField(default=False)
    generacion_bloque_xml = models.BooleanField(default=False)
    seis_decimales = models.BooleanField(default=False)
    importacion_requerida = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["codigo"]
        verbose_name = "Tipo de transacción"
        verbose_name_plural = "Tipos de transacción"

    def __str__(self):
        return f"{self.codigo} - {self.nombre}"
