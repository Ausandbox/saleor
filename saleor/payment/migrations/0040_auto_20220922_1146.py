# Generated by Django 3.2.15 on 2022-09-22 11:46

from decimal import Decimal

import django.contrib.postgres.fields
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("app", "0016_alter_appextension_mount"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("payment", "0039_transactionevent_currency"),
    ]
    operations = [
        migrations.AlterField(
            model_name="transactionitem",
            name="status",
            field=models.CharField(blank=True, default="", max_length=512, null=True),
        ),
        migrations.AddField(
            model_name="transactionitem",
            name="message",
            field=models.CharField(blank=True, default="", null=True, max_length=512),
        ),
        migrations.RenameField(
            model_name="transactionitem",
            old_name="type",
            new_name="name",
        ),
        migrations.AddField(
            model_name="transactionitem",
            name="app_identifier",
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
        migrations.AddField(
            model_name="transactionitem",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="transactionitem",
            name="available_actions",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(
                    choices=[
                        ("charge", "Charge payment"),
                        ("refund", "Refund payment"),
                        ("void", "Void payment"),
                        ("cancel", "Cancel payment"),
                    ],
                    max_length=128,
                ),
                default=list,
                size=None,
            ),
        ),
        migrations.RenameField(
            model_name="transactionitem",
            old_name="reference",
            new_name="psp_reference",
        ),
        migrations.RenameField(
            model_name="transactionitem",
            old_name="voided_value",
            new_name="canceled_value",
        ),
        migrations.AddField(
            model_name="transactionitem",
            name="external_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="transactionevent",
            name="external_url",
            field=models.URLField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="transactionevent",
            name="amount_value",
            field=models.DecimalField(
                decimal_places=3, default=Decimal("0"), max_digits=12
            ),
        ),
        migrations.AlterField(
            model_name="transactionevent",
            name="currency",
            field=models.CharField(max_length=3),
        ),
        migrations.RenameField(
            model_name="transactionevent",
            old_name="name",
            new_name="message",
        ),
        migrations.RenameField(
            model_name="transactionevent",
            old_name="reference",
            new_name="psp_reference",
        ),
        migrations.AlterField(
            model_name="transactionevent",
            name="created_at",
            field=models.DateTimeField(default=django.utils.timezone.now),
        ),
        migrations.AlterField(
            model_name="transactionevent",
            name="status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("pending", "Pending"),
                    ("success", "Success"),
                    ("failure", "Failure"),
                ],
                default="success",
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="transactionevent",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="transactionevent",
            name="app_identifier",
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
        migrations.AddField(
            model_name="transactionevent",
            name="include_in_calculations",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="transactionevent",
            name="type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("authorization_success", "Represents success authorization"),
                    ("authorization_failure", "Represents failure authorization"),
                    ("authorization_adjustment", "Represents authorization adjustment"),
                    ("authorization_request", "Represents authorization request"),
                    ("charge_success", "Represents success charge"),
                    ("charge_failure", "Represents failure charge"),
                    ("charge_back", "Represents chargeback."),
                    ("charge_request", "Represents charge request"),
                    ("refund_success", "Represents success refund"),
                    ("refund_failure", "Represents failure refund"),
                    ("refund_reverse", "Represents reverse refund"),
                    ("refund_request", "Represents refund request"),
                    ("cancel_success", "Represents success cancel"),
                    ("cancel_failure", "Represents failure cancel"),
                    ("cancel_request", "Represents cancel request"),
                ],
                max_length=128,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="transactionitem",
            name="refund_pending_value",
            field=models.DecimalField(
                decimal_places=3, default=Decimal("0"), max_digits=12
            ),
        ),
        migrations.AddField(
            model_name="transactionitem",
            name="authorize_pending_value",
            field=models.DecimalField(
                decimal_places=3, default=Decimal("0"), max_digits=12
            ),
        ),
        migrations.AddField(
            model_name="transactionitem",
            name="cancel_pending_value",
            field=models.DecimalField(
                decimal_places=3, default=Decimal("0"), max_digits=12
            ),
        ),
        migrations.AddField(
            model_name="transactionitem",
            name="charge_pending_value",
            field=models.DecimalField(
                decimal_places=3, default=Decimal("0"), max_digits=12
            ),
        ),
    ]
