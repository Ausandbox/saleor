import graphene
from django.core.exceptions import ValidationError
from django.db import transaction

from ....account.models import User
from ....core.exceptions import InsufficientStock
from ....core.permissions import OrderPermissions
from ....core.taxes import TaxError, zero_taxed_money
from ....core.tracing import traced_atomic_transaction
from ....core.transactions import transaction_with_commit_on_errors
from ....giftcard.utils import deactivate_order_gift_cards, order_has_gift_card_lines
from ....order import FulfillmentStatus, OrderLineData, OrderStatus, events, models
from ....order.actions import (
    cancel_order,
    capture_payments,
    mark_order_as_paid,
    order_confirmed,
    order_shipping_updated,
    refund_payments,
    void_payments,
)
from ....order.error_codes import OrderErrorCode
from ....order.interface import OrderPaymentAction
from ....order.utils import (
    add_variant_to_order,
    change_order_line_quantity,
    delete_order_line,
    get_active_payments,
    get_authorized_payments,
    get_valid_shipping_methods_for_order,
    recalculate_order,
    update_order_prices,
)
from ....payment.model_helpers import get_total_authorized
from ....shipping import models as shipping_models
from ...account.types import AddressInput
from ...core.descriptions import ADDED_IN_31, DEPRECATED_IN_3X_INPUT
from ...core.mutations import BaseMutation, ModelMutation
from ...core.scalars import PositiveDecimal
from ...core.types.common import OrderError
from ...core.utils import validate_required_string_field
from ...order.mutations.draft_orders import (
    DraftOrderCreate,
    OrderLineCreateInput,
    OrderLineInput,
)
from ...product.types import ProductVariant
from ...shipping.types import ShippingMethod
from ..types import Order, OrderEvent, OrderLine
from ..utils import (
    validate_product_is_published_in_channel,
    validate_variant_channel_listings,
)

ORDER_EDITABLE_STATUS = (OrderStatus.DRAFT, OrderStatus.UNCONFIRMED)


def clean_order_update_shipping(order, method):
    if not order.shipping_address:
        raise ValidationError(
            {
                "order": ValidationError(
                    "Cannot choose a shipping method for an order without "
                    "the shipping address.",
                    code=OrderErrorCode.ORDER_NO_SHIPPING_ADDRESS,
                )
            }
        )

    valid_methods = get_valid_shipping_methods_for_order(order)
    if valid_methods is None or method.pk not in valid_methods.values_list(
        "id", flat=True
    ):
        raise ValidationError(
            {
                "shipping_method": ValidationError(
                    "Shipping method cannot be used with this order.",
                    code=OrderErrorCode.SHIPPING_METHOD_NOT_APPLICABLE,
                )
            }
        )


def clean_order_cancel(order):
    if order and not order.can_cancel():
        raise ValidationError(
            {
                "order": ValidationError(
                    "This order can't be canceled.",
                    code=OrderErrorCode.CANNOT_CANCEL_ORDER,
                )
            }
        )


def clean_payments(payments):
    if not payments:
        raise ValidationError(
            {
                "payments": ValidationError(
                    "There are no active payments associated with the order.",
                    code=OrderErrorCode.PAYMENT_MISSING,
                )
            }
        )


def clean_order_capture(order, payments, amount):
    if amount <= 0:
        raise ValidationError(
            {
                "amount": ValidationError(
                    "Amount should be a positive number.",
                    code=OrderErrorCode.ZERO_QUANTITY,
                )
            }
        )

    clean_payments(payments)

    if order.outstanding_balance.amount < amount:
        raise ValidationError(
            {
                "amount": ValidationError(
                    "Amount should less than the outstanding balance.",
                    code=OrderErrorCode.AMOUNT_TOO_HIGH,
                )
            }
        )

    if get_total_authorized(payments, order.currency).amount < amount:
        raise ValidationError(
            {
                "amount": ValidationError(
                    "Amount should less than or equal the authorized amount.",
                    code=OrderErrorCode.AMOUNT_TOO_HIGH,
                )
            }
        )


def clean_void_payments(payments):
    """Check for payment errors."""
    clean_payments(payments)
    if not all([p.is_authorized for p in payments]):
        raise ValidationError(
            {
                "payments": ValidationError(
                    "The order has active payments with status other than authorized.",
                    code=OrderErrorCode.PAYMENT_ERROR.value,
                )
            }
        )


def clean_refund_payments(payments):
    clean_payments(payments)
    for payment in payments:
        if not payment.can_refund():
            raise ValidationError(
                {
                    "payment": ValidationError(
                        "Payment cannot be refunded.",
                        code=OrderErrorCode.CANNOT_REFUND,
                    )
                }
            )


def clean_order_refund(order):
    if order_has_gift_card_lines(order):
        raise ValidationError(
            {
                "id": ValidationError(
                    "Cannot refund order with gift card lines.",
                    code=OrderErrorCode.CANNOT_REFUND.value,
                )
            }
        )


def get_webhook_handler_by_order_status(status, info):
    if status == OrderStatus.DRAFT:
        return info.context.plugins.draft_order_updated
    else:
        return info.context.plugins.order_updated


class OrderUpdateInput(graphene.InputObjectType):
    billing_address = AddressInput(description="Billing address of the customer.")
    user_email = graphene.String(description="Email address of the customer.")
    shipping_address = AddressInput(description="Shipping address of the customer.")


class OrderUpdate(DraftOrderCreate):
    class Arguments:
        id = graphene.ID(required=True, description="ID of an order to update.")
        input = OrderUpdateInput(
            required=True, description="Fields required to update an order."
        )

    class Meta:
        description = "Updates an order."
        model = models.Order
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    def clean_input(cls, info, instance, data):
        draft_order_cleaned_input = super().clean_input(info, instance, data)

        # We must to filter out field added by DraftOrderUpdate
        editable_fields = ["billing_address", "shipping_address", "user_email"]
        cleaned_input = {}
        for key in draft_order_cleaned_input:
            if key in editable_fields:
                cleaned_input[key] = draft_order_cleaned_input[key]
        return cleaned_input

    @classmethod
    def get_instance(cls, info, **data):
        instance = super().get_instance(info, **data)
        if instance.status == OrderStatus.DRAFT:
            raise ValidationError(
                {
                    "id": ValidationError(
                        "Provided order id belongs to draft order. "
                        "Use `draftOrderUpdate` mutation instead.",
                        code=OrderErrorCode.INVALID,
                    )
                }
            )
        return instance

    @classmethod
    @traced_atomic_transaction()
    def save(cls, info, instance, cleaned_input):
        cls._save_addresses(info, instance, cleaned_input)
        if instance.user_email:
            user = User.objects.filter(email=instance.user_email).first()
            instance.user = user
        instance.save()
        update_order_prices(
            instance,
            info.context.plugins,
            info.context.site.settings.include_taxes_in_prices,
        )
        transaction.on_commit(lambda: info.context.plugins.order_updated(instance))


class OrderUpdateShippingInput(graphene.InputObjectType):
    shipping_method = graphene.ID(
        description="ID of the selected shipping method,"
        " pass null to remove currently assigned shipping method.",
        name="shippingMethod",
    )


class EditableOrderValidationMixin:
    class Meta:
        abstract = True

    @classmethod
    def validate_order(cls, order):
        if order.status not in ORDER_EDITABLE_STATUS:
            raise ValidationError(
                {
                    "id": ValidationError(
                        "Only draft and unconfirmed orders can be edited.",
                        code=OrderErrorCode.NOT_EDITABLE,
                    )
                }
            )


class OrderUpdateShipping(EditableOrderValidationMixin, BaseMutation):
    order = graphene.Field(Order, description="Order with updated shipping method.")

    class Arguments:
        id = graphene.ID(
            required=True,
            name="order",
            description="ID of the order to update a shipping method.",
        )
        input = OrderUpdateShippingInput(
            description="Fields required to change shipping method of the order.",
            required=True,
        )

    class Meta:
        description = (
            "Updates a shipping method of the order."
            " Requires shipping method ID to update, when null is passed "
            "then currently assigned shipping method is removed."
        )
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        order = cls.get_node_or_error(
            info,
            data.get("id"),
            only_type=Order,
            qs=models.Order.objects.prefetch_related("lines"),
        )
        cls.validate_order(order)

        data = data.get("input")

        if "shipping_method" not in data:
            raise ValidationError(
                {
                    "shipping_method": ValidationError(
                        "Shipping method must be provided to perform mutation.",
                        code=OrderErrorCode.SHIPPING_METHOD_REQUIRED,
                    )
                }
            )

        if not data.get("shipping_method"):
            if not order.is_draft() and order.is_shipping_required():
                raise ValidationError(
                    {
                        "shipping_method": ValidationError(
                            "Shipping method is required for this order.",
                            code=OrderErrorCode.SHIPPING_METHOD_REQUIRED,
                        )
                    }
                )

            # Shipping method is detached only when null is passed in input.
            if data["shipping_method"] == "":
                raise ValidationError(
                    {
                        "shipping_method": ValidationError(
                            "Shipping method cannot be empty.",
                            code=OrderErrorCode.SHIPPING_METHOD_REQUIRED,
                        )
                    }
                )

            order.shipping_method = None
            order.shipping_price = zero_taxed_money(order.currency)
            order.shipping_method_name = None
            order.save(
                update_fields=[
                    "currency",
                    "shipping_method",
                    "shipping_price_net_amount",
                    "shipping_price_gross_amount",
                    "shipping_method_name",
                ]
            )
            recalculate_order(order)
            return OrderUpdateShipping(order=order)

        method = cls.get_node_or_error(
            info,
            data["shipping_method"],
            field="shipping_method",
            only_type=ShippingMethod,
            qs=shipping_models.ShippingMethod.objects.prefetch_related(
                "postal_code_rules"
            ),
        )

        clean_order_update_shipping(order, method)

        order.shipping_method = method
        shipping_price = info.context.plugins.calculate_order_shipping(order)
        order.shipping_price = shipping_price
        order.shipping_tax_rate = info.context.plugins.get_order_shipping_tax_rate(
            order, shipping_price
        )
        order.shipping_method_name = method.name
        order.save(
            update_fields=[
                "currency",
                "shipping_method",
                "shipping_method_name",
                "shipping_price_net_amount",
                "shipping_price_gross_amount",
                "shipping_tax_rate",
            ]
        )
        update_order_prices(
            order,
            info.context.plugins,
            info.context.site.settings.include_taxes_in_prices,
        )
        # Post-process the results
        order_shipping_updated(order, info.context.plugins)
        return OrderUpdateShipping(order=order)


class OrderAddNoteInput(graphene.InputObjectType):
    message = graphene.String(
        description="Note message.", name="message", required=True
    )


class OrderAddNote(BaseMutation):
    order = graphene.Field(Order, description="Order with the note added.")
    event = graphene.Field(OrderEvent, description="Order note created.")

    class Arguments:
        id = graphene.ID(
            required=True,
            description="ID of the order to add a note for.",
            name="order",
        )
        input = OrderAddNoteInput(
            required=True, description="Fields required to create a note for the order."
        )

    class Meta:
        description = "Adds note to the order."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    def clean_input(cls, _info, _instance, data):
        try:
            cleaned_input = validate_required_string_field(data["input"], "message")
        except ValidationError:
            raise ValidationError(
                {
                    "message": ValidationError(
                        "Message can't be empty.",
                        code=OrderErrorCode.REQUIRED,
                    )
                }
            )
        return cleaned_input

    @classmethod
    @traced_atomic_transaction()
    def perform_mutation(cls, _root, info, **data):
        order = cls.get_node_or_error(info, data.get("id"), only_type=Order)
        cleaned_input = cls.clean_input(info, order, data)
        event = events.order_note_added_event(
            order=order,
            user=info.context.user,
            app=info.context.app,
            message=cleaned_input["message"],
        )
        func = get_webhook_handler_by_order_status(order.status, info)
        transaction.on_commit(lambda: func(order))
        return OrderAddNote(order=order, event=event)


class OrderCancel(BaseMutation):
    order = graphene.Field(Order, description="Canceled order.")

    class Arguments:
        id = graphene.ID(required=True, description="ID of the order to cancel.")

    class Meta:
        description = "Cancel an order."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    @traced_atomic_transaction()
    def perform_mutation(cls, _root, info, **data):
        order = cls.get_node_or_error(info, data.get("id"), only_type=Order)
        clean_order_cancel(order)
        user = info.context.user
        app = info.context.app
        cancel_order(
            order=order,
            user=user,
            app=app,
            manager=info.context.plugins,
        )
        deactivate_order_gift_cards(order.id, user, app)
        return OrderCancel(order=order)


class OrderMarkAsPaid(BaseMutation):
    order = graphene.Field(Order, description="Order marked as paid.")

    class Arguments:
        id = graphene.ID(required=True, description="ID of the order to mark paid.")
        transaction_reference = graphene.String(
            required=False, description="The external transaction reference."
        )

    class Meta:
        description = "Mark order as manually paid."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    def clean_billing_address(cls, instance):
        if not instance.billing_address:
            raise ValidationError(
                "Order billing address is required to mark order as paid.",
                code=OrderErrorCode.BILLING_ADDRESS_NOT_SET,
            )

    @classmethod
    def clean_order(cls, app, order, user):
        if not order.payments.exists():
            return

        message = "Orders with payments can not be manually marked as paid."
        events.payment_capture_failed_event(
            order=order, user=user, app=app, message=message, payment=None, amount=None
        )
        raise ValidationError(
            {"payment": ValidationError(message, code=OrderErrorCode.PAYMENT_ERROR)}
        )

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        order = cls.get_node_or_error(info, data.get("id"), only_type=Order)
        transaction_reference = data.get("transaction_reference")
        user = info.context.user
        app = info.context.app
        cls.clean_billing_address(order)
        cls.clean_order(app, order, user)

        mark_order_as_paid(
            order, user, app, info.context.plugins, transaction_reference
        )
        return OrderMarkAsPaid(order=order)


class OrderCapture(BaseMutation):
    order = graphene.Field(Order, description="Captured order.")

    class Arguments:
        id = graphene.ID(required=True, description="ID of the order to capture.")
        amount = PositiveDecimal(
            required=True, description="Amount of money to capture."
        )

    class Meta:
        description = "Capture an order."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    def perform_mutation(cls, _root, info, amount, **data):
        order = cls.get_node_or_error(
            info,
            data.get("id"),
            only_type=Order,
            qs=models.Order.objects.prefetch_related("payments"),
        )
        payments = get_authorized_payments(order)
        clean_order_capture(order, payments, amount)
        manager = info.context.plugins
        payment_errors = capture_payments(
            order,
            info.context.user,
            info.context.app,
            manager,
        )
        if payment_errors:
            messages = [e.message for e in payment_errors]
            raise ValidationError(
                " ".join(messages),
                code=OrderErrorCode.PAYMENT_ERROR.value,
            )
        return OrderCapture(order=order)


class OrderVoid(BaseMutation):
    order = graphene.Field(Order, description="A voided order.")

    class Arguments:
        id = graphene.ID(required=True, description="ID of the order to void.")

    class Meta:
        description = "Void an order."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    def perform_mutation(cls, _root, info, **data):
        order = cls.get_node_or_error(
            info,
            data.get("id"),
            only_type=Order,
            qs=models.Order.objects.prefetch_related("payments"),
        )
        payments = [p for p in get_active_payments(order)]
        clean_void_payments(payments)
        manager = info.context.plugins
        payment_errors = void_payments(
            order,
            info.context.user,
            info.context.app,
            manager,
        )
        if payment_errors:
            messages = [e.message for e in payment_errors]
            raise ValidationError(
                " ".join(messages),
                code=OrderErrorCode.PAYMENT_ERROR.value,
            )
        return OrderVoid(order=order)


class OrderPaymentToRefundInput(graphene.InputObjectType):
    payment_id = graphene.ID(required=True, description="The GraphQL ID of a payment.")
    amount = PositiveDecimal(required=True, description="Amount of the refund.")


class OrderRefund(BaseMutation):
    order = graphene.Field(Order, description="A refunded order.")

    class Arguments:
        id = graphene.ID(required=True, description="ID of the order to refund.")
        amount = PositiveDecimal(
            required=False,
            description=(
                f"Amount of money to refund. "
                f"{DEPRECATED_IN_3X_INPUT} Use `paymentsToRefund` instead."
            ),
        )
        payments_to_refund = graphene.List(
            graphene.NonNull(OrderPaymentToRefundInput),
            required=False,
            description=f"{ADDED_IN_31} Payments that need to be refunded.",
        )

    class Meta:
        description = "Refund an order."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    def _run_checks(cls, amount, payments_to_refund):
        if (not amount and not payments_to_refund) or (amount and payments_to_refund):
            raise ValidationError(
                {
                    "amount": ValidationError(
                        "Either amount or payments_to_refund should be specified.",
                        code=OrderErrorCode.TOO_MANY_OR_NONE_FIELDS_SPECIFIED,
                    ),
                    "payments_to_refund": ValidationError(
                        "Either amount or payments_to_refund should be specified.",
                        code=OrderErrorCode.TOO_MANY_OR_NONE_FIELDS_SPECIFIED,
                    ),
                }
            )
        if amount and amount <= 0:
            raise ValidationError(
                {
                    "amount": ValidationError(
                        "Amount should be a positive number.",
                        code=OrderErrorCode.ZERO_QUANTITY,
                    )
                }
            )

    @classmethod
    def _check_total_amount_to_refund(cls, payments, amount=None):
        total_captured_amount = sum([item.payment.captured_amount for item in payments])
        if amount and amount > total_captured_amount:
            raise ValidationError(
                {
                    "amount": ValidationError(
                        "The total amount to refund cannot be bigger "
                        "than the total captured amount.",
                        code=OrderErrorCode.AMOUNT_TOO_HIGH,
                    )
                }
            )

    @classmethod
    def _check_amount_to_refund_per_payment(cls, payments):
        improper_payments_ids = []
        for item in payments:
            if item.payment.captured_amount < item.amount:
                improper_payments_ids.append(
                    graphene.Node.to_global_id("Payment", item.payment.id)
                )

        if improper_payments_ids:
            raise ValidationError(
                {
                    "amount": ValidationError(
                        "The amount to refund cannot be bigger "
                        "than the captured amount.",
                        code=OrderErrorCode.AMOUNT_TOO_HIGH,
                        params={"payments": improper_payments_ids},
                    )
                }
            )

    @classmethod
    def _prepare_payments(cls, info, order, amount, payments_to_refund):
        if payments_to_refund:
            payments = [
                OrderPaymentAction(
                    cls.get_node_or_error(info, item["payment_id"]),
                    item["amount"],
                )
                for item in payments_to_refund
                if item["amount"] > 0
            ]

            if not payments:
                raise ValidationError(
                    {
                        "amount": ValidationError(
                            "The total amount to refund of the specified payments "
                            "has to be higher than zero.",
                            code=OrderErrorCode.ZERO_QUANTITY.value,
                        )
                    }
                )

            cls._check_amount_to_refund_per_payment(payments)

        else:
            active_payments = order.payments.filter(is_active=True)
            payments = [
                OrderPaymentAction(
                    payment,
                    payment.captured_amount,
                )
                for payment in active_payments
            ]
            cls._check_total_amount_to_refund(payments, amount)

        return payments

    @classmethod
    @transaction_with_commit_on_errors()
    def perform_mutation(
        cls, _root, info, amount=None, payments_to_refund=None, **data
    ):
        cls._run_checks(amount, payments_to_refund)

        order = cls.get_node_or_error(info, data.get("id"), only_type=Order)
        payments = cls._prepare_payments(info, order, amount, payments_to_refund)
        clean_order_refund(order)
        clean_refund_payments([item.payment for item in payments])

        manager = info.context.plugins
        refunded_payments, _ = refund_payments(
            order,
            payments,
            info.context.user,
            info.context.app,
            manager,
        )

        total_amount = sum([item.amount for item in refunded_payments])
        if total_amount:
            order.fulfillments.create(
                status=FulfillmentStatus.REFUNDED, total_refund_amount=total_amount
            )
            transaction.on_commit(lambda: manager.order_updated(order))

        return OrderRefund(order=order)


class OrderConfirm(ModelMutation):
    order = graphene.Field(Order, description="Order which has been confirmed.")

    class Arguments:
        id = graphene.ID(description="ID of an order to confirm.", required=True)

    class Meta:
        description = "Confirms an unconfirmed order by changing status to unfulfilled."
        model = models.Order
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    def get_instance(cls, info, **data):
        instance = super().get_instance(info, **data)
        if not instance.is_unconfirmed():
            raise ValidationError(
                {
                    "id": ValidationError(
                        "Provided order id belongs to an order with status "
                        "different than unconfirmed.",
                        code=OrderErrorCode.INVALID,
                    )
                }
            )
        if not instance.lines.exists():
            raise ValidationError(
                {
                    "id": ValidationError(
                        "Provided order id belongs to an order without products.",
                        code=OrderErrorCode.INVALID,
                    )
                }
            )
        return instance

    @classmethod
    @traced_atomic_transaction()
    def perform_mutation(cls, root, info, **data):
        order = cls.get_instance(info, **data)
        order.status = OrderStatus.UNFULFILLED
        order.save(update_fields=["status"])
        manager = info.context.plugins
        order_confirmed(
            order,
            info.context.user,
            info.context.app,
            manager,
            send_confirmation_email=True,
        )
        return OrderConfirm(order=order)


class OrderLinesCreate(EditableOrderValidationMixin, BaseMutation):
    order = graphene.Field(Order, description="Related order.")
    order_lines = graphene.List(
        graphene.NonNull(OrderLine), description="List of added order lines."
    )

    class Arguments:
        id = graphene.ID(
            required=True, description="ID of the order to add the lines to."
        )
        input = graphene.List(
            OrderLineCreateInput,
            required=True,
            description="Fields required to add order lines.",
        )

    class Meta:
        description = "Create order lines for an order."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"
        errors_mapping = {"lines": "input", "channel": "input"}

    @classmethod
    def validate_lines(cls, info, data):
        lines_to_add = []
        invalid_ids = []
        for input_line in data.get("input"):
            variant_id = input_line["variant_id"]
            variant = cls.get_node_or_error(
                info, variant_id, "variant_id", only_type=ProductVariant
            )
            quantity = input_line["quantity"]
            if quantity > 0:
                lines_to_add.append((quantity, variant))
            else:
                invalid_ids.append(variant_id)
        if invalid_ids:
            raise ValidationError(
                {
                    "quantity": ValidationError(
                        "Variants quantity must be greater than 0.",
                        code=OrderErrorCode.ZERO_QUANTITY,
                        params={"variants": invalid_ids},
                    ),
                }
            )
        return lines_to_add

    @classmethod
    def validate_variants(cls, order, variants):
        try:
            channel = order.channel
            validate_product_is_published_in_channel(variants, channel)
            validate_variant_channel_listings(variants, channel)
        except ValidationError as error:
            cls.remap_error_fields(error, cls._meta.errors_mapping)
            raise ValidationError(error)

    @staticmethod
    def add_lines_to_order(order, lines_to_add, user, app, manager):
        try:
            return [
                add_variant_to_order(
                    order,
                    variant,
                    quantity,
                    user,
                    app,
                    manager,
                    allocate_stock=order.is_unconfirmed(),
                )
                for quantity, variant in lines_to_add
            ]
        except TaxError as tax_error:
            raise ValidationError(
                "Unable to calculate taxes - %s" % str(tax_error),
                code=OrderErrorCode.TAX_ERROR.value,
            )

    @classmethod
    @traced_atomic_transaction()
    def perform_mutation(cls, _root, info, **data):
        order = cls.get_node_or_error(info, data.get("id"), only_type=Order)
        cls.validate_order(order)
        lines_to_add = cls.validate_lines(info, data)
        variants = [line[1] for line in lines_to_add]
        cls.validate_variants(order, variants)

        lines = cls.add_lines_to_order(
            order,
            lines_to_add,
            info.context.user,
            info.context.app,
            info.context.plugins,
        )

        # Create the products added event
        events.order_added_products_event(
            order=order,
            user=info.context.user,
            app=info.context.app,
            order_lines=lines_to_add,
        )

        recalculate_order(order)

        func = get_webhook_handler_by_order_status(order.status, info)
        transaction.on_commit(lambda: func(order))

        return OrderLinesCreate(order=order, order_lines=lines)


class OrderLineDelete(EditableOrderValidationMixin, BaseMutation):
    order = graphene.Field(Order, description="A related order.")
    order_line = graphene.Field(
        OrderLine, description="An order line that was deleted."
    )

    class Arguments:
        id = graphene.ID(description="ID of the order line to delete.", required=True)

    class Meta:
        description = "Deletes an order line from an order."
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    @traced_atomic_transaction()
    def perform_mutation(cls, _root, info, id):
        manager = info.context.plugins
        line = cls.get_node_or_error(
            info,
            id,
            only_type=OrderLine,
        )
        order = line.order
        cls.validate_order(line.order)

        db_id = line.id
        warehouse_pk = (
            line.allocations.first().stock.warehouse.pk
            if order.is_unconfirmed()
            else None
        )
        line_info = OrderLineData(
            line=line,
            quantity=line.quantity,
            variant=line.variant,
            warehouse_pk=warehouse_pk,
        )
        delete_order_line(line_info, manager)
        line.id = db_id

        if not order.is_shipping_required():
            order.shipping_method = None
            order.shipping_price = zero_taxed_money(order.currency)
            order.shipping_method_name = None
            order.save(
                update_fields=[
                    "currency",
                    "shipping_method",
                    "shipping_price_net_amount",
                    "shipping_price_gross_amount",
                    "shipping_method_name",
                ]
            )
        # Create the removal event
        events.order_removed_products_event(
            order=order,
            user=info.context.user,
            app=info.context.app,
            order_lines=[(line.quantity, line)],
        )

        recalculate_order(order)
        func = get_webhook_handler_by_order_status(order.status, info)
        transaction.on_commit(lambda: func(order))
        return OrderLineDelete(order=order, order_line=line)


class OrderLineUpdate(EditableOrderValidationMixin, ModelMutation):
    order = graphene.Field(Order, description="Related order.")

    class Arguments:
        id = graphene.ID(description="ID of the order line to update.", required=True)
        input = OrderLineInput(
            required=True, description="Fields required to update an order line."
        )

    class Meta:
        description = "Updates an order line of an order."
        model = models.OrderLine
        permissions = (OrderPermissions.MANAGE_ORDERS,)
        error_type_class = OrderError
        error_type_field = "order_errors"

    @classmethod
    def clean_input(cls, info, instance, data):
        instance.old_quantity = instance.quantity
        cleaned_input = super().clean_input(info, instance, data)
        cls.validate_order(instance.order)

        quantity = data["quantity"]
        if quantity <= 0:
            raise ValidationError(
                {
                    "quantity": ValidationError(
                        "Ensure this value is greater than 0.",
                        code=OrderErrorCode.ZERO_QUANTITY,
                    )
                }
            )
        return cleaned_input

    @classmethod
    @traced_atomic_transaction()
    def save(cls, info, instance, cleaned_input):
        manager = info.context.plugins
        warehouse_pk = (
            instance.allocations.first().stock.warehouse.pk
            if instance.order.is_unconfirmed()
            else None
        )
        line_info = OrderLineData(
            line=instance,
            quantity=instance.quantity,
            variant=instance.variant,
            warehouse_pk=warehouse_pk,
        )
        try:
            change_order_line_quantity(
                info.context.user,
                info.context.app,
                line_info,
                instance.old_quantity,
                instance.quantity,
                instance.order.channel.slug,
                manager,
            )
        except InsufficientStock:
            raise ValidationError(
                "Cannot set new quantity because of insufficient stock.",
                code=OrderErrorCode.INSUFFICIENT_STOCK,
            )
        recalculate_order(instance.order)

        func = get_webhook_handler_by_order_status(instance.order.status, info)
        transaction.on_commit(lambda: func(instance.order))

    @classmethod
    def success_response(cls, instance):
        response = super().success_response(instance)
        response.order = instance.order
        return response
