# Generated by Django 3.2.12 on 2022-05-24 04:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('product', '0151_productchannellisting_product_pro_discoun_3145f3_btree'),
    ]

    operations = [
        migrations.AddField(
            model_name='productvariant',
            name='orgin_variant_id',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
        migrations.AddField(
            model_name='productvariant',
            name='origin_sku',
            field=models.CharField(blank=True, max_length=255, null=True),
        ),
    ]
