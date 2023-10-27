# Generated by Django 3.2.21 on 2023-09-26 08:46

from django.db import migrations
from django.contrib.postgres.operations import AddIndexConcurrently
from django.contrib.postgres.indexes import BTreeIndex


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("discount", "0058_vouchercustomer_vouchercode"),
    ]

    operations = [
        AddIndexConcurrently(
            model_name="vouchercustomer",
            index=BTreeIndex(
                fields=["voucher_code"], name="vouchercustomer_voucher_code_idx"
            ),
        ),
    ]
