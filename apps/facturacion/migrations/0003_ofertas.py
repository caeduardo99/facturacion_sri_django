from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("clientes", "0001_initial"),
        ("productos", "0001_initial"),
        ("facturacion", "0002_configurar_establecimiento_punto"),
    ]

    operations = [
        migrations.CreateModel(
            name="Oferta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("numero", models.CharField(blank=True, max_length=20, unique=True)),
                ("fecha", models.DateField(default=django.utils.timezone.localdate)),
                ("estado", models.CharField(choices=[("BORRADOR", "Borrador"), ("APROBADA", "Aprobada"), ("FACTURADA", "Facturada"), ("ANULADA", "Anulada")], default="BORRADOR", max_length=12)),
                ("subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("iva", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("creado", models.DateTimeField(auto_now_add=True)),
                ("actualizado", models.DateTimeField(auto_now=True)),
                ("cliente", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ofertas", to="clientes.cliente")),
            ],
            options={"ordering": ["-id"]},
        ),
        migrations.CreateModel(
            name="DetalleOferta",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("codigo", models.CharField(max_length=50)),
                ("descripcion", models.CharField(max_length=300)),
                ("cantidad", models.DecimalField(decimal_places=4, max_digits=14)),
                ("precio_unitario", models.DecimalField(decimal_places=4, max_digits=14)),
                ("subtotal", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("iva", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("total", models.DecimalField(decimal_places=2, default=0, max_digits=14)),
                ("oferta", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="detalles", to="facturacion.oferta")),
                ("producto", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to="productos.producto")),
            ],
        ),
        migrations.AddField(
            model_name="comprobante",
            name="oferta",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="comprobantes", to="facturacion.oferta"),
        ),
    ]
