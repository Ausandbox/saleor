from decimal import Decimal
from unittest.mock import create_autospec, patch

import graphql
import pytest
from django.core.exceptions import ValidationError
from prices import Money, TaxedMoney

from ...order import OrderLineData
from ...payment import ChargeStatus, TransactionKind
from ...payment.models import Payment
from ...plugins.manager import get_plugins_manager
from ...product.models import DigitalContent
from ...product.tests.utils import create_image
from ...warehouse.models import Allocation, Stock
from .. import FulfillmentStatus, OrderEvents, OrderStatus
from ..actions import (
    _add_missing_amounts_on_payments,
    _process_refund,
    _refund_payments,
    automatically_fulfill_digital_lines,
    cancel_fulfillment,
    cancel_order,
    fulfill_order_lines,
    handle_fully_paid_order,
    mark_order_as_paid,
    refund_payments,
)
from ..error_codes import OrderErrorCode
from ..interface import OrderPaymentAction
from ..models import Fulfillment
from ..notifications import (
    send_fulfillment_confirmation_to_customer,
    send_payment_confirmation,
)


@pytest.fixture
def order_with_digital_line(order, digital_content, stock, site_settings):
    site_settings.automatic_fulfillment_digital_products = True
    site_settings.save()

    variant = stock.product_variant
    variant.digital_content = digital_content
    variant.digital_content.save()

    product_type = variant.product.product_type
    product_type.is_shipping_required = False
    product_type.is_digital = True
    product_type.save()

    quantity = 3
    product = variant.product
    channel = order.channel
    variant_channel_listing = variant.channel_listings.get(channel=channel)
    net = variant.get_price(product, [], channel, variant_channel_listing, None)
    gross = Money(amount=net.amount * Decimal(1.23), currency=net.currency)
    unit_price = TaxedMoney(net=net, gross=gross)
    line = order.lines.create(
        product_name=str(product),
        variant_name=str(variant),
        product_sku=variant.sku,
        product_variant_id=variant.get_global_id(),
        is_shipping_required=variant.is_shipping_required(),
        is_gift_card=variant.is_gift_card(),
        quantity=quantity,
        variant=variant,
        unit_price=unit_price,
        total_price=unit_price * quantity,
        tax_rate=Decimal("0.23"),
    )

    Allocation.objects.create(order_line=line, stock=stock, quantity_allocated=quantity)

    return order


@patch(
    "saleor.order.actions.send_fulfillment_confirmation_to_customer",
    wraps=send_fulfillment_confirmation_to_customer,
)
@patch(
    "saleor.order.actions.send_payment_confirmation", wraps=send_payment_confirmation
)
def test_handle_fully_paid_order_digital_lines(
    mock_send_payment_confirmation,
    send_fulfillment_confirmation_to_customer,
    order_with_digital_line,
):
    order = order_with_digital_line
    order.payments.add(Payment.objects.create())
    redirect_url = "http://localhost.pl"
    order = order_with_digital_line
    order.redirect_url = redirect_url
    order.save()
    manager = get_plugins_manager()
    handle_fully_paid_order(manager, order)

    fulfillment = order.fulfillments.first()
    event_order_paid = order.events.get()

    assert event_order_paid.type == OrderEvents.ORDER_FULLY_PAID

    mock_send_payment_confirmation.assert_called_once_with(order, manager)
    send_fulfillment_confirmation_to_customer.assert_called_once_with(
        order, fulfillment, user=order.user, app=None, manager=manager
    )

    order.refresh_from_db()
    assert order.status == OrderStatus.FULFILLED


@patch("saleor.order.actions.send_payment_confirmation")
def test_handle_fully_paid_order(mock_send_payment_confirmation, order):
    manager = get_plugins_manager()

    order.payments.add(Payment.objects.create())
    handle_fully_paid_order(manager, order)
    event_order_paid = order.events.get()

    assert event_order_paid.type == OrderEvents.ORDER_FULLY_PAID

    mock_send_payment_confirmation.assert_called_once_with(order, manager)


@patch("saleor.order.notifications.send_payment_confirmation")
def test_handle_fully_paid_order_no_email(mock_send_payment_confirmation, order):
    order.user = None
    order.user_email = ""
    manager = get_plugins_manager()

    handle_fully_paid_order(manager, order)
    event = order.events.get()
    assert event.type == OrderEvents.ORDER_FULLY_PAID
    assert not mock_send_payment_confirmation.called


def test_mark_as_paid(admin_user, draft_order):
    manager = get_plugins_manager()
    mark_order_as_paid(draft_order, admin_user, None, manager)
    payment = draft_order.payments.last()
    assert payment.charge_status == ChargeStatus.FULLY_CHARGED
    assert payment.captured_amount == draft_order.total.gross.amount
    assert draft_order.events.last().type == (OrderEvents.ORDER_MARKED_AS_PAID)
    transactions = payment.transactions.all()
    assert transactions.count() == 1
    assert transactions[0].kind == TransactionKind.EXTERNAL


def test_mark_as_paid_with_external_reference(admin_user, draft_order):
    external_reference = "transaction_id"
    manager = get_plugins_manager()
    mark_order_as_paid(
        draft_order, admin_user, None, manager, external_reference=external_reference
    )
    payment = draft_order.payments.last()
    assert payment.charge_status == ChargeStatus.FULLY_CHARGED
    assert payment.captured_amount == draft_order.total.gross.amount
    assert payment.psp_reference == external_reference
    assert draft_order.events.last().type == (OrderEvents.ORDER_MARKED_AS_PAID)
    transactions = payment.transactions.all()
    assert transactions.count() == 1
    assert transactions[0].kind == TransactionKind.EXTERNAL
    assert transactions[0].token == external_reference


def test_mark_as_paid_no_billing_address(admin_user, draft_order):
    draft_order.billing_address = None
    draft_order.save()

    manager = get_plugins_manager()
    with pytest.raises(Exception):
        mark_order_as_paid(draft_order, admin_user, None, manager)


def test_cancel_fulfillment(fulfilled_order, warehouse):
    fulfillment = fulfilled_order.fulfillments.first()
    line_1, line_2 = fulfillment.lines.all()

    cancel_fulfillment(fulfillment, None, None, warehouse, get_plugins_manager())

    fulfillment.refresh_from_db()
    fulfilled_order.refresh_from_db()
    assert fulfillment.status == FulfillmentStatus.CANCELED
    assert fulfilled_order.status == OrderStatus.UNFULFILLED
    assert line_1.order_line.quantity_fulfilled == 0
    assert line_2.order_line.quantity_fulfilled == 0


def test_cancel_fulfillment_variant_witout_inventory_tracking(
    fulfilled_order_without_inventory_tracking, warehouse
):
    fulfillment = fulfilled_order_without_inventory_tracking.fulfillments.first()
    line = fulfillment.lines.first()
    stock = line.order_line.variant.stocks.get()
    stock_quantity_before = stock.quantity

    cancel_fulfillment(fulfillment, None, None, warehouse, get_plugins_manager())

    fulfillment.refresh_from_db()
    line.refresh_from_db()
    fulfilled_order_without_inventory_tracking.refresh_from_db()
    assert fulfillment.status == FulfillmentStatus.CANCELED
    assert line.order_line.quantity_fulfilled == 0
    assert fulfilled_order_without_inventory_tracking.status == OrderStatus.UNFULFILLED
    assert stock_quantity_before == line.order_line.variant.stocks.get().quantity


@patch("saleor.order.actions.send_order_canceled_confirmation")
def test_cancel_order(
    send_order_canceled_confirmation_mock,
    fulfilled_order_with_all_cancelled_fulfillments,
):
    # given
    order = fulfilled_order_with_all_cancelled_fulfillments
    manager = get_plugins_manager()

    assert Allocation.objects.filter(
        order_line__order=order, quantity_allocated__gt=0
    ).exists()

    # when
    cancel_order(order, None, None, manager)

    # then
    order_event = order.events.last()
    assert order_event.type == OrderEvents.CANCELED

    assert order.status == OrderStatus.CANCELED
    assert not Allocation.objects.filter(
        order_line__order=order, quantity_allocated__gt=0
    ).exists()

    send_order_canceled_confirmation_mock.assert_called_once_with(
        order, None, None, manager
    )


@patch("saleor.order.actions.gateway.refund")
def test_refund_payments_calls_gateway_refund_for_each_payment(
    try_refund_mock,
    order,
    checkout_with_item,
    app,
):
    # given
    num_of_payments = 2
    money = Money(amount=Decimal("60"), currency=order.currency)
    order.total = TaxedMoney(money, money)
    order.save()
    amount = order.total.gross.amount / num_of_payments
    for _ in range(num_of_payments):
        payment = Payment.objects.create(
            gateway="mirumee.payments.dummy",
            is_active=True,
            checkout=checkout_with_item,
            currency=order.currency,
            captured_amount=amount,
            charge_status=ChargeStatus.FULLY_CHARGED,
        )
        payment.transactions.create(
            amount=payment.captured_amount,
            currency=payment.currency,
            kind=TransactionKind.CAPTURE,
            gateway_response={},
            is_success=True,
        )

    payments = Payment.objects.all()
    payments = [OrderPaymentAction(payment, amount) for payment in payments]

    # when
    info = create_autospec(graphql.execution.base.ResolveInfo)
    info.context.app = app
    info.context.plugins = get_plugins_manager()
    refund_payments(
        order, payments, info.context.user, info.context.app, info.context.plugins
    )

    # then
    assert try_refund_mock.call_count == num_of_payments


@patch("saleor.order.actions._refund_payments")
def test_refund_payments_raises_error_if_no_payments_have_been_refunded(
    _refund_payments_mock,
    order,
    checkout_with_item,
    app,
):
    # given
    num_of_payments = 2
    money = Money(amount=Decimal("60"), currency=order.currency)
    order.total = TaxedMoney(money, money)
    order.save()
    amount = order.total.gross.amount / num_of_payments
    for _ in range(num_of_payments):
        payment = Payment.objects.create(
            gateway="mirumee.payments.dummy",
            is_active=True,
            checkout=checkout_with_item,
            currency=order.currency,
            captured_amount=amount,
            charge_status=ChargeStatus.FULLY_CHARGED,
        )
        payment.transactions.create(
            amount=payment.captured_amount,
            currency=payment.currency,
            kind=TransactionKind.CAPTURE,
            gateway_response={},
            is_success=True,
        )

    payments = Payment.objects.all()
    payments = [OrderPaymentAction(payment, amount) for payment in payments]

    payment_errors = ["Error 1", "Error 2"]
    _refund_payments_mock.return_value = [], payment_errors

    # when
    info = create_autospec(graphql.execution.base.ResolveInfo)
    info.context.app = app
    info.context.plugins = get_plugins_manager()
    with pytest.raises(ValidationError) as err:
        refund_payments(
            order, payments, info.context.user, info.context.app, info.context.plugins
        )

    # then
    assert err.value.error_dict["payments"][0].message == (
        f"The refund operation is not available yet "
        f"for {len(payment_errors)} payments."
    )
    assert (
        err.value.error_dict["payments"][0].code == OrderErrorCode.CANNOT_REFUND.value
    )


@patch("saleor.order.actions._refund_payments")
def test_refund_payments_does_not_raise_error_if_one_payment_has_been_refunded(
    _refund_payments_mock,
    order,
    checkout_with_item,
    app,
):
    # given
    num_of_payments = 2
    money = Money(amount=Decimal("60"), currency=order.currency)
    order.total = TaxedMoney(money, money)
    order.save()
    amount = order.total.gross.amount / num_of_payments
    for _ in range(num_of_payments):
        payment = Payment.objects.create(
            gateway="mirumee.payments.dummy",
            is_active=True,
            checkout=checkout_with_item,
            currency=order.currency,
            captured_amount=amount,
            charge_status=ChargeStatus.FULLY_CHARGED,
        )
        payment.transactions.create(
            amount=payment.captured_amount,
            currency=payment.currency,
            kind=TransactionKind.CAPTURE,
            gateway_response={},
            is_success=True,
        )

    payments = Payment.objects.all()
    payments = [OrderPaymentAction(payment, amount) for payment in payments]

    payment_errors = ["Error 1", "Error 2"]
    _refund_payments_mock.return_value = [payments[0]], payment_errors

    # when
    info = create_autospec(graphql.execution.base.ResolveInfo)
    info.context.app = app
    info.context.plugins = get_plugins_manager()
    payments, errors = refund_payments(
        order, payments, info.context.user, info.context.app, info.context.plugins
    )

    # then
    assert payments == [payments[0]]
    assert errors == payment_errors


def test_fulfill_order_lines(order_with_lines):
    order = order_with_lines
    line = order.lines.first()
    quantity_fulfilled_before = line.quantity_fulfilled
    variant = line.variant
    stock = Stock.objects.get(product_variant=variant)
    stock_quantity_after = stock.quantity - line.quantity

    fulfill_order_lines(
        [
            OrderLineData(
                line=line,
                quantity=line.quantity,
                variant=variant,
                warehouse_pk=stock.warehouse.pk,
            )
        ],
        get_plugins_manager(),
    )

    stock.refresh_from_db()
    assert stock.quantity == stock_quantity_after
    assert line.quantity_fulfilled == quantity_fulfilled_before + line.quantity


def test_fulfill_order_lines_multiple_lines(order_with_lines):
    order = order_with_lines
    lines = order.lines.all()

    assert lines.count() > 1

    quantity_fulfilled_before_1 = lines[0].quantity_fulfilled
    variant_1 = lines[0].variant
    stock_1 = Stock.objects.get(product_variant=variant_1)
    stock_quantity_after_1 = stock_1.quantity - lines[0].quantity

    quantity_fulfilled_before_2 = lines[1].quantity_fulfilled
    variant_2 = lines[1].variant
    stock_2 = Stock.objects.get(product_variant=variant_2)
    stock_quantity_after_2 = stock_2.quantity - lines[1].quantity

    fulfill_order_lines(
        [
            OrderLineData(
                line=lines[0],
                quantity=lines[0].quantity,
                variant=variant_1,
                warehouse_pk=stock_1.warehouse.pk,
            ),
            OrderLineData(
                line=lines[1],
                quantity=lines[1].quantity,
                variant=variant_2,
                warehouse_pk=stock_2.warehouse.pk,
            ),
        ],
        get_plugins_manager(),
    )

    stock_1.refresh_from_db()
    assert stock_1.quantity == stock_quantity_after_1
    assert (
        lines[0].quantity_fulfilled == quantity_fulfilled_before_1 + lines[0].quantity
    )

    stock_2.refresh_from_db()
    assert stock_2.quantity == stock_quantity_after_2
    assert (
        lines[1].quantity_fulfilled == quantity_fulfilled_before_2 + lines[1].quantity
    )


def test_fulfill_order_lines_with_variant_deleted(order_with_lines):
    line = order_with_lines.lines.first()
    line.variant.delete()

    line.refresh_from_db()

    fulfill_order_lines(
        [OrderLineData(line=line, quantity=line.quantity)], get_plugins_manager()
    )


def test_fulfill_order_lines_without_inventory_tracking(order_with_lines):
    order = order_with_lines
    line = order.lines.first()
    quantity_fulfilled_before = line.quantity_fulfilled
    variant = line.variant
    variant.track_inventory = False
    variant.save()
    stock = Stock.objects.get(product_variant=variant)

    # stock should not change
    stock_quantity_after = stock.quantity

    fulfill_order_lines(
        [
            OrderLineData(
                line=line,
                quantity=line.quantity,
                variant=variant,
                warehouse_pk=stock.warehouse.pk,
            )
        ],
        get_plugins_manager(),
    )

    stock.refresh_from_db()
    assert stock.quantity == stock_quantity_after
    assert line.quantity_fulfilled == quantity_fulfilled_before + line.quantity


@patch("saleor.order.actions.send_fulfillment_confirmation_to_customer")
@patch("saleor.order.utils.get_default_digital_content_settings")
def test_fulfill_digital_lines(
    mock_digital_settings, mock_email_fulfillment, order_with_lines, media_root
):
    mock_digital_settings.return_value = {"automatic_fulfillment": True}
    line = order_with_lines.lines.all()[0]

    image_file, image_name = create_image()
    variant = line.variant
    digital_content = DigitalContent.objects.create(
        content_file=image_file, product_variant=variant, use_default_settings=True
    )

    line.variant.digital_content = digital_content
    line.is_shipping_required = False
    line.save()

    order_with_lines.refresh_from_db()
    manager = get_plugins_manager()

    automatically_fulfill_digital_lines(order_with_lines, manager)

    line.refresh_from_db()
    fulfillment = Fulfillment.objects.get(order=order_with_lines)
    fulfillment_lines = fulfillment.lines.all()

    assert fulfillment_lines.count() == 1
    assert line.digital_content_url
    assert mock_email_fulfillment.called


@patch("saleor.order.actions._refund_payments")
@patch("saleor.order.actions._calculate_refund_amount")
@patch("saleor.order.actions._add_missing_amounts_on_payments")
def test_process_refund_calls_add_missing_amounts_on_payments(
    _add_missing_amounts_on_payments_mock,
    _calculate_refund_amount_mock,
    _refund_payments_mock,
    order_with_lines,
    payment_dummy_fully_charged,
    staff_user,
):
    order_with_lines.payments.add(payment_dummy_fully_charged)
    payment = order_with_lines.payments.last()
    payments = [OrderPaymentAction(payment, Decimal("0"))]

    order_lines_to_return = order_with_lines.lines.all()

    refund_amount = Decimal("500")
    _calculate_refund_amount_mock.return_value = refund_amount
    _add_missing_amounts_on_payments_mock.return_value = refund_amount, None
    _refund_payments_mock.return_value = payments, []

    _process_refund(
        user=staff_user,
        app=None,
        order=order_with_lines,
        payments=payments,
        order_lines_to_refund=[
            OrderLineData(line=line, quantity=2, replace=False)
            for line in order_lines_to_return
        ],
        fulfillment_lines_to_refund=[],
        manager=get_plugins_manager(),
        include_shipping_costs=False,
    )
    _add_missing_amounts_on_payments_mock.assert_called_once_with(
        refund_amount, payments, order_with_lines, False
    )


@patch("saleor.order.actions.__refund_payment_or_create_event")
def test_refunding_is_not_called_for_payments_with_zero_amounts(
    refund_mock, order_with_lines, payment_dummy_fully_charged, payment_txn_captured
):
    refund_mock.return_value = None, None
    order_with_lines.payments.add(payment_dummy_fully_charged)
    order_with_lines.payments.add(payment_txn_captured)
    payment_1 = OrderPaymentAction(
        payment=payment_dummy_fully_charged,
        amount=payment_dummy_fully_charged.captured_amount,
    )
    payment_2 = OrderPaymentAction(payment=payment_txn_captured, amount=Decimal("0"))
    payments = [payment_1, payment_2]
    manager = get_plugins_manager()

    _refund_payments(order_with_lines, payments, manager, None, None)

    refund_mock.assert_called_once_with(
        order_with_lines, payment_1.payment, payment_1.amount, manager, None, None
    )


def test_update_missing_amounts_on_payments_with_specified_payment_amounts(
    order_with_lines, payment_dummy_fully_charged, payment_txn_captured
):
    # given
    order_with_lines.payments.add(payment_dummy_fully_charged)
    order_with_lines.payments.add(payment_txn_captured)
    refund_amount = (
        payment_dummy_fully_charged.captured_amount
        + payment_txn_captured.captured_amount
    )
    payments = [
        OrderPaymentAction(
            payment_dummy_fully_charged,
            payment_dummy_fully_charged.captured_amount,
        ),
        OrderPaymentAction(
            payment_txn_captured,
            payment_txn_captured.captured_amount,
        ),
    ]

    # when
    total_refund_amount, shipping_refund_amount = _add_missing_amounts_on_payments(
        refund_amount, payments, order_with_lines, include_shipping_costs=False
    )

    # then
    assert total_refund_amount == refund_amount
    assert shipping_refund_amount is None
    assert payments[0].amount == payment_dummy_fully_charged.captured_amount
    assert payments[0].amount == payment_txn_captured.captured_amount


def test_update_missing_amounts_on_payments_with_shipping_amount_multiple_payments(
    order_with_lines, payment_dummy_fully_charged, payment_txn_captured
):
    # given
    order_with_lines.payments.add(payment_dummy_fully_charged)
    order_with_lines.payments.add(payment_txn_captured)
    refund_amount = payment_txn_captured.captured_amount

    payments = [
        OrderPaymentAction(
            payment_dummy_fully_charged,
            Decimal("0"),
        ),
        OrderPaymentAction(
            payment_txn_captured,
            payment_txn_captured.captured_amount,
        ),
    ]

    # when
    total_refund_amount, shipping_refund_amount = _add_missing_amounts_on_payments(
        refund_amount, payments, order_with_lines, include_shipping_costs=True
    )

    # then
    assert (
        total_refund_amount
        == refund_amount + order_with_lines.shipping_price_gross_amount
    )
    assert shipping_refund_amount == order_with_lines.shipping_price_gross_amount
    assert payments[0].amount == order_with_lines.shipping_price_gross_amount
    assert payments[1].amount == payment_txn_captured.captured_amount


def test_update_missing_amounts_on_payments_with_shipping_amount_and_single_payment(
    order_with_lines, payment_dummy_fully_charged
):
    # given
    order_with_lines.payments.add(payment_dummy_fully_charged)
    payment_dummy_fully_charged.captured_amount += (
        order_with_lines.shipping_price_gross_amount
    )
    payment_dummy_fully_charged.save()
    refund_amount = (
        payment_dummy_fully_charged.captured_amount
        - order_with_lines.shipping_price_gross_amount
    )
    payments = [OrderPaymentAction(payment_dummy_fully_charged, Decimal("0"))]

    # when
    total_refund_amount, shipping_refund_amount = _add_missing_amounts_on_payments(
        refund_amount, payments, order_with_lines, include_shipping_costs=True
    )

    # then
    assert (
        total_refund_amount
        == refund_amount + order_with_lines.shipping_price_gross_amount
    )
    assert shipping_refund_amount == order_with_lines.shipping_price_gross_amount
    assert (
        payments[0].amount
        == refund_amount + order_with_lines.shipping_price_gross_amount
    )


def test_update_missing_amounts_on_payments_without_specified_amounts(
    order_with_lines, payment_dummy_fully_charged, payment_txn_captured
):
    # given
    order_with_lines.payments.add(payment_dummy_fully_charged)
    order_with_lines.payments.add(payment_txn_captured)
    refund_amount = (
        payment_dummy_fully_charged.captured_amount
        + payment_txn_captured.captured_amount
    )
    payments = [
        OrderPaymentAction(
            payment_dummy_fully_charged,
            Decimal("0"),
        ),
        OrderPaymentAction(
            payment_txn_captured,
            Decimal("0"),
        ),
    ]

    # when
    total_refund_amount, shipping_refund_amount = _add_missing_amounts_on_payments(
        refund_amount, payments, order_with_lines, include_shipping_costs=False
    )

    # then
    assert total_refund_amount == refund_amount
    assert shipping_refund_amount is None
    assert payments[0].amount == payment_dummy_fully_charged.captured_amount
    assert payments[1].amount == payment_txn_captured.captured_amount


def test_update_missing_amounts_on_payments_refunding_smaller_amounts(
    order_with_lines, payment_dummy_fully_charged, payment_txn_captured
):
    # given
    order_with_lines.payments.add(payment_dummy_fully_charged)
    order_with_lines.payments.add(payment_txn_captured)
    refund_amount = (
        payment_dummy_fully_charged.captured_amount
        + payment_txn_captured.captured_amount
    )

    payments = [
        OrderPaymentAction(
            payment_dummy_fully_charged,
            payment_dummy_fully_charged.captured_amount // 2,
        ),
        OrderPaymentAction(
            payment_txn_captured,
            payment_txn_captured.captured_amount // 2,
        ),
    ]

    # when
    total_refund_amount, shipping_refund_amount = _add_missing_amounts_on_payments(
        refund_amount, payments, order_with_lines, include_shipping_costs=False
    )

    # then
    assert total_refund_amount == refund_amount // 2
    assert shipping_refund_amount is None
    assert payments[0].amount == payment_dummy_fully_charged.captured_amount // 2
    assert payments[1].amount == payment_txn_captured.captured_amount // 2
