from django.db import migrations, models


class Migration(migrations.Migration):
    # Se ejecuta después de las migraciones que ya existen en la instalación.
    dependencies = [
        ("facturacion", "0003_comprobante_estado_transaccion"),
    ]

    operations = [
        migrations.AddField(
            model_name="comprobante",
            name="codigo_transaccion",
            field=models.CharField(default="FE", max_length=10),
        ),
    ]
