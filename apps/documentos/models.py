from django.db import models
class Documento(models.Model):
    comprobante=models.ForeignKey('facturacion.Comprobante',on_delete=models.CASCADE,related_name='documentos'); tipo=models.CharField(max_length=20); archivo=models.FileField(upload_to='documentos/'); creado=models.DateTimeField(auto_now_add=True)
