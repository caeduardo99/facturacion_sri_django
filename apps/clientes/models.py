from django.db import models
class Cliente(models.Model):
    TIPO_CHOICES=[('05','Cédula'),('04','RUC'),('06','Pasaporte'),('07','Consumidor final')]
    tipo_identificacion=models.CharField(max_length=2,choices=TIPO_CHOICES,default='05'); identificacion=models.CharField(max_length=20,unique=True); nombres=models.CharField(max_length=250); direccion=models.CharField(max_length=300,blank=True); telefono=models.CharField(max_length=50,blank=True); email=models.EmailField(blank=True); activo=models.BooleanField(default=True); creado=models.DateTimeField(auto_now_add=True); actualizado=models.DateTimeField(auto_now=True)
    def __str__(self): return f'{self.identificacion} - {self.nombres}'
