from django.db import models
class Producto(models.Model):
    codigo=models.CharField(max_length=50,unique=True); codigo_auxiliar=models.CharField(max_length=50,blank=True); nombre=models.CharField(max_length=250); descripcion=models.TextField(blank=True); precio=models.DecimalField(max_digits=14,decimal_places=4,default=0); porcentaje_iva=models.DecimalField(max_digits=5,decimal_places=2,default=15); stock=models.DecimalField(max_digits=14,decimal_places=4,default=0); activo=models.BooleanField(default=True)
    def __str__(self): return f'{self.codigo} - {self.nombre}'
