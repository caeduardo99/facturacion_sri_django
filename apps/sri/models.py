from django.db import models
class TransmisionSRI(models.Model):
    ESTADOS=[('PENDIENTE','Pendiente'),('RECIBIDA','Recibida'),('AUTORIZADO','Autorizado'),('RECHAZADO','Rechazado'),('ERROR','Error')]
    comprobante=models.ForeignKey('facturacion.Comprobante',on_delete=models.CASCADE,related_name='transmisiones_sri'); fecha_envio=models.DateTimeField(null=True,blank=True); fecha_autorizacion=models.DateTimeField(null=True,blank=True); estado=models.CharField(max_length=20,choices=ESTADOS,default='PENDIENTE'); ambiente=models.PositiveSmallIntegerField(default=1); respuesta_recepcion=models.TextField(blank=True); respuesta_autorizacion=models.TextField(blank=True); intentos=models.PositiveIntegerField(default=0); actualizado=models.DateTimeField(auto_now=True)
