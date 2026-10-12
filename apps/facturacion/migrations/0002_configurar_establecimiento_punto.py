from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("facturacion", "0001_add_codigo_transaccion"),
    ]

    operations = [
        migrations.AddField(
            model_name="tipotransaccion",
            name="establecimiento",
            field=models.CharField(
                default="001",
                help_text="Establecimiento autorizado por el SRI para esta transacción",
                max_length=3,
            ),
        ),
        migrations.AddField(
            model_name="tipotransaccion",
            name="punto_emision",
            field=models.CharField(
                default="001",
                help_text="Punto de emisión autorizado por el SRI para esta transacción",
                max_length=3,
            ),
        ),
    ]
