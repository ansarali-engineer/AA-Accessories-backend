from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("orders", "0002_alter_order_status_payment_shipment"),
    ]

    operations = [
        migrations.AddField(
            model_name="order",
            name="payment_method",
            field=models.CharField(
                choices=[("card", "Card"), ("cash_on_delivery", "Cash on delivery")],
                default="card",
                max_length=20,
            ),
        ),
    ]
