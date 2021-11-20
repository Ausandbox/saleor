import logging
from decimal import Decimal
from unittest import mock

import graphene
import pytest

from ......checkout import calculations
from ......checkout.fetch import fetch_checkout_info, fetch_checkout_lines
from ......order import OrderEvents, OrderStatus
from ......plugins.manager import get_plugins_manager
from ..... import ChargeStatus, TransactionKind
from .....utils import price_to_minor_unit
from ...webhooks import (
    create_new_transaction,
    handle_authorization,
    handle_cancel_or_refund,
    handle_cancellation,
    handle_capture,
    handle_failed_capture,
    handle_failed_refund,
    handle_not_created_order,
    handle_pending,
    handle_refund,
    handle_reversed_refund,
    webhook_not_implemented,
)

logger = logging.getLogger(__name__)


def test_handle_authorization_for_order(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    handle_authorization(notification, config)

    assert payment.transactions.count() == 2
    transaction = payment.transactions.last()
    assert transaction.is_success is True
    assert transaction.kind == TransactionKind.AUTH
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_authorization_for_order_invalid_payment_id(
    notification, adyen_plugin, payment_adyen_for_order, caplog
):
    payment = payment_adyen_for_order
    invalid_reference = "test invalid reference"
    notification = notification(
        merchant_reference=invalid_reference,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    transaction_count = payment.transactions.count()

    caplog.set_level(logging.WARNING)

    handle_authorization(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == transaction_count
    assert f"Unable to decode the payment ID {invalid_reference}." in caplog.text


def test_handle_multiple_authorization_notification(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.NOT_CHARGED
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    first_notification = notification(
        merchant_reference=payment_id,
        success="false",
        psp_reference="wrong",
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin(adyen_auto_capture=True).config
    handle_authorization(first_notification, config)

    payment.refresh_from_db()
    assert payment.charge_status == ChargeStatus.NOT_CHARGED
    capture_transaction = payment.transactions.get(kind=TransactionKind.CAPTURE)
    assert capture_transaction.is_success is False
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1

    second_notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    handle_authorization(second_notification, config)
    payment.refresh_from_db()
    assert payment.charge_status == ChargeStatus.FULLY_CHARGED
    assert payment.captured_amount == payment.total
    capture_transaction = payment.transactions.filter(
        kind=TransactionKind.CAPTURE
    ).last()
    assert capture_transaction.is_success is True
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 2


def test_handle_authorization_for_pending_order(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.PENDING
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin(adyen_auto_capture=True).config
    handle_authorization(notification, config)

    assert payment.transactions.count() == 2
    transaction = payment.transactions.last()
    assert transaction.is_success is True
    assert transaction.kind == TransactionKind.CAPTURE
    payment.refresh_from_db()
    assert payment.charge_status == ChargeStatus.FULLY_CHARGED
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_authorization_for_checkout(
    notification,
    adyen_plugin,
    payment_adyen_for_checkout,
    address,
    shipping_method,
):
    checkout = payment_adyen_for_checkout.checkout
    checkout.shipping_address = address
    checkout.shipping_method = shipping_method
    checkout.billing_address = address
    checkout.save()
    checkout_token = str(checkout.token)

    payment = payment_adyen_for_checkout
    manager = get_plugins_manager()
    lines = fetch_checkout_lines(checkout)
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)
    total = calculations.calculate_checkout_total_with_gift_cards(
        manager, checkout_info, lines, address
    )
    payment.is_active = True
    payment.order = None
    payment.total = total.gross.amount
    payment.currency = total.gross.currency
    payment.to_confirm = True
    payment.save()

    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    handle_authorization(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == 2
    transaction = payment.transactions.exclude(
        kind=TransactionKind.ACTION_TO_CONFIRM
    ).get()
    assert transaction.is_success is True
    assert transaction.kind == TransactionKind.AUTH
    assert payment.checkout is None
    assert payment.order
    assert payment.order.checkout_token == checkout_token
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_authorization_with_adyen_auto_capture(
    notification, adyen_plugin, payment_adyen_for_checkout, address, shipping_method
):
    checkout = payment_adyen_for_checkout.checkout
    checkout.shipping_address = address
    checkout.shipping_method = shipping_method
    checkout.billing_address = address
    checkout.save()

    payment = payment_adyen_for_checkout
    manager = get_plugins_manager()
    lines = fetch_checkout_lines(checkout)
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)
    total = calculations.calculate_checkout_total_with_gift_cards(
        manager, checkout_info, lines, address
    )
    payment.is_active = True
    payment.order = None
    payment.total = total.gross.amount
    payment.currency = total.gross.currency
    payment.to_confirm = True
    payment.save()

    payment_id = graphene.Node.to_global_id("Payment", payment.pk)

    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )

    plugin = adyen_plugin(adyen_auto_capture=True)
    handle_authorization(notification, plugin.config)

    payment.refresh_from_db()
    assert payment.transactions.count() == 2
    transaction = payment.transactions.filter(kind=TransactionKind.CAPTURE).get()
    assert transaction.is_success is True
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


@pytest.mark.vcr
def test_handle_authorization_with_auto_capture(
    notification, adyen_plugin, payment_adyen_for_checkout
):
    payment = payment_adyen_for_checkout
    payment.to_confirm = True
    payment.save()

    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        psp_reference="853596537720508F",
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin(adyen_auto_capture=False, auto_capture=True).config

    handle_authorization(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == 2
    transaction = payment.transactions.filter(kind=TransactionKind.CAPTURE).get()
    assert transaction.is_success is True
    assert payment.charge_status == ChargeStatus.FULLY_CHARGED
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_authorization_with_adyen_auto_capture_and_payment_charged(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    config.connection_params["adyen_auto_capture"] = True
    handle_authorization(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == 2
    assert payment.transactions.filter(kind=TransactionKind.CAPTURE).exists()
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


@pytest.mark.parametrize("payment_is_active", (True, False))
def test_handle_cancel(
    payment_is_active, notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.is_active = payment_is_active
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    manager = get_plugins_manager()

    handle_cancellation(notification, config, manager)

    payment.order.refresh_from_db()
    assert payment.transactions.count() == 2
    transaction = payment.transactions.filter(kind=TransactionKind.CANCEL).get()
    assert transaction.is_success is True

    assert payment.order.status == OrderStatus.CANCELED
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_cancel_invalid_payment_id(
    notification, adyen_plugin, payment_adyen_for_order, caplog
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    invalid_reference = "test invalid reference"
    notification = notification(
        merchant_reference=invalid_reference,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    transaction_count = payment.transactions.count()

    caplog.set_level(logging.WARNING)
    manager = get_plugins_manager()

    handle_cancellation(notification, config, manager)

    payment.order.refresh_from_db()
    assert payment.transactions.count() == transaction_count

    payment.refresh_from_db()
    assert payment.transactions.count() == transaction_count
    assert f"Unable to decode the payment ID {invalid_reference}." in caplog.text


def test_handle_cancel_already_canceled(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    create_new_transaction(notification, payment, TransactionKind.CANCEL)
    manager = get_plugins_manager()

    handle_cancellation(notification, config, manager)

    assert payment.transactions.count() == 2


def test_handle_capture_for_order(notification, adyen_plugin, payment_adyen_for_order):
    payment = payment_adyen_for_order
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    handle_capture(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == 2
    transaction = payment.transactions.filter(kind=TransactionKind.CAPTURE).get()
    assert transaction.is_success is True
    assert payment.charge_status == ChargeStatus.FULLY_CHARGED
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_capture_for_checkout(
    notification,
    adyen_plugin,
    payment_adyen_for_checkout,
    address,
    shipping_method,
):
    checkout = payment_adyen_for_checkout.checkout
    checkout.shipping_address = address
    checkout.shipping_method = shipping_method
    checkout.billing_address = address
    checkout.save()
    checkout_token = str(checkout.token)

    payment = payment_adyen_for_checkout
    manager = get_plugins_manager()
    lines = fetch_checkout_lines(checkout)
    checkout_info = fetch_checkout_info(checkout, lines, [], manager)
    total = calculations.calculate_checkout_total_with_gift_cards(
        manager, checkout_info, lines, address
    )
    payment.is_active = True
    payment.order = None
    payment.total = total.gross.amount
    payment.currency = total.gross.currency
    payment.to_confirm = True
    payment.save()

    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    handle_capture(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == 2
    transaction = payment.transactions.exclude(
        kind=TransactionKind.ACTION_TO_CONFIRM
    ).get()
    assert transaction.is_success is True
    assert transaction.kind == TransactionKind.AUTH
    assert payment.checkout is None
    assert payment.order
    assert payment.order.checkout_token == checkout_token
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_capture_invalid_payment_id(
    notification, adyen_plugin, payment_adyen_for_order, caplog
):
    payment = payment_adyen_for_order
    invalid_reference = "test invalid reference"
    notification = notification(
        merchant_reference=invalid_reference,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    transaction_count = payment.transactions.count()

    caplog.set_level(logging.WARNING)

    handle_capture(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == transaction_count
    assert f"Unable to decode the payment ID {invalid_reference}." in caplog.text


def test_handle_capture_with_payment_already_charged(
    notification, adyen_plugin, payment_adyen_for_order
):
    # given
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.captured_amount = payment.total
    payment.save()
    payment.transactions.create(
        action_required=False,
        kind=TransactionKind.CAPTURE,
        is_success=True,
        amount=payment.total,
        currency=payment.currency,
        gateway_response={},
    )

    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config

    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    transactions_count = payment.transactions.count()
    external_events_count = external_events.count()

    # when
    handle_capture(notification, config)

    # then
    payment.refresh_from_db()
    # FIXME a duplicate notification should be probably ignored
    assert payment.transactions.count() == transactions_count + 1
    assert external_events.count() == external_events_count + 1
    assert payment.captured_amount == payment.total


@pytest.mark.parametrize(
    "charge_status", [ChargeStatus.NOT_CHARGED, ChargeStatus.FULLY_CHARGED]
)
def test_handle_failed_capture(
    charge_status, notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = charge_status
    payment.captured_amount = payment.total
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config

    handle_failed_capture(notification, config)

    assert payment.transactions.count() == 2
    transaction = payment.transactions.filter(kind=TransactionKind.CAPTURE_FAILED).get()
    assert transaction.is_success is True
    payment.refresh_from_db()
    assert payment.charge_status == ChargeStatus.NOT_CHARGED
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_failed_capture_invalid_payment_id(
    notification, adyen_plugin, payment_adyen_for_order, caplog
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.captured_amount = payment.total
    payment.save()
    invalid_reference = "test invalid reference"
    notification = notification(
        merchant_reference=invalid_reference,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    transaction_count = payment.transactions.count()

    caplog.set_level(logging.WARNING)

    handle_failed_capture(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == transaction_count
    assert f"Unable to decode the payment ID {invalid_reference}." in caplog.text


def test_handle_failed_capture_partial_charge(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.captured_amount += payment.total * 2
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config

    handle_failed_capture(notification, config)

    assert payment.transactions.count() == 2
    transaction = payment.transactions.filter(kind=TransactionKind.CAPTURE_FAILED).get()
    assert transaction.is_success is True
    payment.refresh_from_db()
    assert payment.charge_status == ChargeStatus.PARTIALLY_CHARGED
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_pending(notification, adyen_plugin, payment_adyen_for_order):
    payment = payment_adyen_for_order
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config

    handle_pending(notification, config)

    assert payment.transactions.count() == 2
    transaction = payment.transactions.filter(kind=TransactionKind.PENDING).get()
    assert transaction.is_success is True
    payment.refresh_from_db()
    assert payment.charge_status == ChargeStatus.PENDING
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_pending_invalid_payment_id(
    notification, adyen_plugin, payment_adyen_for_order, caplog
):
    payment = payment_adyen_for_order
    invalid_reference = "test invalid reference"
    notification = notification(
        merchant_reference=invalid_reference,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    transaction_count = payment.transactions.count()

    caplog.set_level(logging.WARNING)

    handle_pending(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == transaction_count
    assert f"Unable to decode the payment ID {invalid_reference}." in caplog.text


def test_handle_pending_with_adyen_auto_capture(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    config.connection_params["adyen_auto_capture"] = True

    handle_pending(notification, config)

    # in case of autocapture we don't want to store the pending status as all payments
    # by default get capture status.
    assert payment.transactions.count() == 2
    assert payment.transactions.filter(kind=TransactionKind.PENDING).first()
    payment.refresh_from_db()
    assert payment.charge_status == ChargeStatus.PENDING
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_pending_already_pending(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.PENDING
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    create_new_transaction(notification, payment, TransactionKind.PENDING)

    handle_pending(notification, config)

    assert payment.transactions.filter(kind=TransactionKind.PENDING).exists()


def test_handle_refund(notification, adyen_plugin, payment_adyen_for_order):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.captured_amount = payment.total
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config

    handle_refund(notification, config)

    assert payment.transactions.count() == 2
    transaction = payment.transactions.filter(kind=TransactionKind.REFUND).get()
    assert transaction.is_success is True
    payment.refresh_from_db()
    assert payment.charge_status == ChargeStatus.FULLY_REFUNDED
    assert payment.captured_amount == Decimal("0.00")

    payment_events = payment.order.events.filter(type=OrderEvents.PAYMENT_REFUNDED)
    assert payment_events.count() == 1

    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_refund_invalid_payment_id(
    notification, adyen_plugin, payment_adyen_for_order, caplog
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.captured_amount = payment.total
    payment.save()
    invalid_reference = "test invalid reference"
    notification = notification(
        merchant_reference=invalid_reference,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    transaction_count = payment.transactions.count()

    caplog.set_level(logging.WARNING)

    handle_refund(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == transaction_count
    assert f"Unable to decode the payment ID {invalid_reference}." in caplog.text


def test_handle_refund_already_refunded(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_REFUNDED
    payment.captured_amount = Decimal("0.00")
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    create_new_transaction(notification, payment, TransactionKind.REFUND)
    config = adyen_plugin().config

    handle_refund(notification, config)

    assert payment.transactions.count() == 2  # AUTH, REFUND

    payment_events = payment.order.events.filter(type=OrderEvents.PAYMENT_REFUNDED)
    assert payment_events.count() == 0


def test_handle_failed_refund_missing_transaction(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.captured_amount = payment.total
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config

    handle_failed_refund(notification, config)

    assert payment.transactions.count() == 1
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_failed_refund_invalid_payment_id(
    notification, adyen_plugin, payment_adyen_for_order, caplog
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.captured_amount = payment.total
    payment.save()
    invalid_reference = "test invalid reference"
    notification = notification(
        merchant_reference=invalid_reference,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    transaction_count = payment.transactions.count()

    caplog.set_level(logging.WARNING)

    handle_failed_refund(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == transaction_count
    assert f"Unable to decode the payment ID {invalid_reference}." in caplog.text


def test_handle_failed_refund_with_transaction_refund_ongoing(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.captured_amount = payment.total
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    create_new_transaction(notification, payment, TransactionKind.REFUND_ONGOING)
    handle_failed_refund(notification, config)

    # ACTION_TO_CONFIRM, REFUND_ONGOING, REFUND_FAILED, FULLY_CHARGED
    assert payment.transactions.count() == 4
    assert payment.charge_status == ChargeStatus.FULLY_CHARGED
    assert payment.total == payment.captured_amount
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_failed_refund_with_transaction_refund(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_REFUNDED
    payment.captured_amount = Decimal("0.0")
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    create_new_transaction(notification, payment, TransactionKind.REFUND)
    handle_failed_refund(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == 4  # REFUND, REFUND_FAILED, FULLY_CHARGED
    assert payment.charge_status == ChargeStatus.FULLY_CHARGED
    assert payment.total == payment.captured_amount
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_reversed_refund(notification, adyen_plugin, payment_adyen_for_order):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_REFUNDED
    payment.captured_amount = Decimal("0.0")
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    handle_reversed_refund(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.filter(kind=TransactionKind.REFUND_REVERSED).exists()
    assert payment.charge_status == ChargeStatus.FULLY_CHARGED
    assert payment.total == payment.captured_amount
    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_handle_reversed_refund_invalid_payment_id(
    notification, adyen_plugin, payment_adyen_for_order, caplog
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_REFUNDED
    payment.captured_amount = Decimal("0.0")
    payment.save()
    invalid_reference = "test invalid reference"
    notification = notification(
        merchant_reference=invalid_reference,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    transaction_count = payment.transactions.count()

    caplog.set_level(logging.WARNING)

    handle_reversed_refund(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == transaction_count
    assert f"Unable to decode the payment ID {invalid_reference}." in caplog.text


def test_handle_reversed_refund_already_processed(
    notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.captured_amount = payment.total
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    create_new_transaction(notification, payment, TransactionKind.REFUND_REVERSED)
    handle_reversed_refund(notification, config)

    assert payment.transactions.filter(kind=TransactionKind.REFUND_REVERSED).exists()


def test_webhook_not_implemented(notification, adyen_plugin, payment_adyen_for_order):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.captured_amount = payment.total
    payment.save()
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config

    webhook_not_implemented(notification, config)

    external_events = payment.order.events.filter(
        type=OrderEvents.EXTERNAL_SERVICE_NOTIFICATION
    )
    assert external_events.count() == 1


def test_webhook_not_implemented_invalid_payment_id(
    notification, adyen_plugin, payment_adyen_for_order, caplog
):
    payment = payment_adyen_for_order
    payment.charge_status = ChargeStatus.FULLY_CHARGED
    payment.captured_amount = payment.total
    payment.save()
    invalid_reference = "test invalid reference"
    notification = notification(
        merchant_reference=invalid_reference,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    config = adyen_plugin().config
    transaction_count = payment.transactions.count()

    caplog.set_level(logging.WARNING)

    webhook_not_implemented(notification, config)

    payment.refresh_from_db()
    assert payment.transactions.count() == transaction_count
    assert f"Unable to decode the payment ID {invalid_reference}." in caplog.text


@mock.patch("saleor.payment.gateways.adyen.webhooks.handle_refund")
def test_handle_cancel_or_refund_action_refund(
    mock_handle_refund, notification, adyen_plugin, payment_adyen_for_order
):

    payment = payment_adyen_for_order
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    config = adyen_plugin().config
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    notification["additionalData"]["modification.action"] = "refund"

    handle_cancel_or_refund(notification, config)

    mock_handle_refund.assert_called_once_with(notification, config)


@mock.patch("saleor.payment.gateways.adyen.webhooks.handle_cancellation")
def test_handle_cancel_or_refund_action_cancel(
    mock_handle_cancellation, notification, adyen_plugin, payment_adyen_for_order
):
    payment = payment_adyen_for_order
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)
    config = adyen_plugin().config
    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    notification["additionalData"]["modification.action"] = "cancel"

    handle_cancel_or_refund(notification, config)

    mock_handle_cancellation.assert_called_once_with(notification, config, mock.ANY)


def test_handle_cancel_or_refund_action_cancel_invalid_payment_id(
    notification, adyen_plugin, payment_adyen_for_order, caplog
):
    payment = payment_adyen_for_order
    config = adyen_plugin().config
    invalid_reference = "test invalid reference"
    notification = notification(
        merchant_reference=invalid_reference,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    notification["additionalData"]["modification.action"] = "cancel"

    caplog.set_level(logging.WARNING)

    handle_cancel_or_refund(notification, config)

    assert f"Unable to decode the payment ID {invalid_reference}." in caplog.text


@mock.patch("saleor.payment.models.Payment.can_create_order")
@mock.patch("saleor.payment.gateways.adyen.webhooks.create_order")
def test_handle_not_created_order_creates_order(
    mock_create_order,
    mock_can_create_order,
    notification,
    payment_adyen_for_checkout,
):
    mock_can_create_order.return_value = True
    payment = payment_adyen_for_checkout
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)

    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    manager = get_plugins_manager()

    handle_not_created_order(
        notification,
        payment,
        payment.checkout,
        TransactionKind.ACTION_TO_CONFIRM,
        manager,
    )

    mock_create_order.assert_called_once_with(payment, payment.checkout, manager)


@mock.patch("saleor.payment.models.Payment.can_create_order")
@mock.patch("saleor.payment.gateways.adyen.webhooks.create_order")
def test_handle_not_created_order_does_not_create_order(
    mock_create_order,
    mock_can_create_order,
    notification,
    payment_adyen_for_checkout,
):
    mock_can_create_order.return_value = False
    payment = payment_adyen_for_checkout
    payment_id = graphene.Node.to_global_id("Payment", payment.pk)

    notification = notification(
        merchant_reference=payment_id,
        value=price_to_minor_unit(payment.total, payment.currency),
    )
    manager = get_plugins_manager()

    handle_not_created_order(
        notification,
        payment,
        payment.checkout,
        TransactionKind.ACTION_TO_CONFIRM,
        manager,
    )

    mock_create_order.assert_not_called()
