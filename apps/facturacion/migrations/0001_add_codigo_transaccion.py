from django.db import migrations, models


class Migration(migrations.Migration):
    # La tabla de comprobantes ya existe en instalaciones actuales.
    # Esta migración agrega únicamente el identificador de transacción.
    dependencies = []

    operations = [
        migrations.AddField(
            model_name="comprobante",
            name="codigo_transaccion",
            field=models.CharField(default="FE", max_length=10),
        ),
    ]
