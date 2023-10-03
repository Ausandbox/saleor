# Generated by Django 3.2.21 on 2023-10-03 10:30

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("discount", "0050_detach_sale_from_permission"),
    ]
    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AlterUniqueTogether(
                    name="salechannellisting",
                    unique_together=None,
                ),
                migrations.RemoveField(
                    model_name="salechannellisting",
                    name="channel",
                ),
                migrations.RemoveField(
                    model_name="salechannellisting",
                    name="sale",
                ),
                migrations.AlterUniqueTogether(
                    name="saletranslation",
                    unique_together=None,
                ),
                migrations.RemoveField(
                    model_name="saletranslation",
                    name="sale",
                ),
                migrations.RemoveField(
                    model_name="checkoutlinediscount",
                    name="sale",
                ),
                migrations.RemoveField(
                    model_name="orderdiscount",
                    name="sale",
                ),
                migrations.RemoveField(
                    model_name="orderlinediscount",
                    name="sale",
                ),
                migrations.DeleteModel(
                    name="Sale",
                ),
                migrations.DeleteModel(
                    name="SaleChannelListing",
                ),
                migrations.DeleteModel(
                    name="SaleTranslation",
                ),
            ]
        ),
    ]
