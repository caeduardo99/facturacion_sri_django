from django.db import models

class Empresa(models.Model):
    ruc = models.CharField(max_length=13, unique=True)
    razon_social = models.CharField(max_length=250)
    nombre_comercial = models.CharField(max_length=250, blank=True)
    direccion_matriz = models.CharField(max_length=300, blank=True)
    obligado_contabilidad = models.BooleanField(default=False)
    activo = models.BooleanField(default=True)
    ambiente_sri = models.PositiveSmallIntegerField(default=1)
    certificado_path = models.CharField(max_length=500, blank=True)
    certificado_password = models.CharField(max_length=255, blank=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.ruc} - {self.razon_social}"

class Establecimiento(models.Model):
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="establecimientos")
    codigo = models.CharField(max_length=3)
    nombre = models.CharField(max_length=150)
    direccion = models.CharField(max_length=300)
    activo = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["empresa", "codigo"], name="uq_establecimiento_empresa_codigo")]

class PuntoEmision(models.Model):
    establecimiento = models.ForeignKey(Establecimiento, on_delete=models.CASCADE, related_name="puntos_emision")
    codigo = models.CharField(max_length=3)
    nombre = models.CharField(max_length=150)
    activo = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["establecimiento", "codigo"], name="uq_punto_establecimiento_codigo")]

class Secuencial(models.Model):
    punto_emision = models.ForeignKey(PuntoEmision, on_delete=models.CASCADE, related_name="secuenciales")
    tipo_comprobante = models.CharField(max_length=2)
    ultimo = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["punto_emision", "tipo_comprobante"], name="uq_secuencial_punto_tipo")]
