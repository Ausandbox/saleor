# Generated by Django 3.1 on 2020-08-19 07:50

import django.db.models.deletion
from django.db import migrations, models
from django.utils.text import slugify


def migrate_products_publishable_data(apps, schema_editor):
    Channel = apps.get_model("channel", "Channel")
    Product = apps.get_model("product", "Product")
    ProductChannelListing = apps.get_model("product", "ProductChannelListing")

    channels_dict = {}

    for product in Product.objects.iterator():
        currency = product.currency
        channel = channels_dict.get(currency)
        if not channel:
            name = f"Channel {currency}"
            channel, _ = Channel.objects.get_or_create(
                currency_code=currency, defaults={"name": name, "slug": slugify(name)},
            )
            channels_dict[currency] = channel
        ProductChannelListing.objects.create(
            product=product,
            channel=channel,
            is_published=product.is_published,
            publication_date=product.publication_date,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("channel", "0001_initial"),
        ("product", "0130_product_variant_channel_listing"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProductChannelListing",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("publication_date", models.DateField(blank=True, null=True)),
                ("is_published", models.BooleanField(default=False)),
                (
                    "channel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="product_listing",
                        to="channel.channel",
                    ),
                ),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="channel_listing",
                        to="product.product",
                    ),
                ),
            ],
            options={"ordering": ("pk",), "unique_together": {("product", "channel")}},
        ),
        migrations.RunPython(migrate_products_publishable_data),
        migrations.RemoveField(model_name="product", name="is_published",),
        migrations.RemoveField(model_name="product", name="publication_date",),
    ]
