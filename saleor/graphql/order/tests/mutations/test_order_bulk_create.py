import copy
from datetime import timedelta
from decimal import Decimal

import graphene
import pytest
from django.utils import timezone

from .....account.models import Address
from .....order import OrderOrigin, OrderStatus
from .....order.error_codes import OrderBulkCreateErrorCode
from .....order.models import Order, OrderEvent, OrderLine
from ....core.enums import ErrorPolicyEnum
from ....tests.utils import get_graphql_content
from ...bulk_mutations.order_bulk_create import MINUTES_DIFF

ORDER_BULK_CREATE = """
    mutation OrderBulkCreate(
        $orders: [OrderBulkCreateInput!]!,
        $errorPolicy: ErrorPolicyEnum
    ) {
        orderBulkCreate(orders: $orders, errorPolicy: $errorPolicy) {
            count
            results {
                order {
                    id
                    user {
                        id
                        email
                    }
                    lines {
                        id
                        variant {
                            id
                        }
                        productName
                        variantName
                        translatedVariantName
                        translatedProductName
                        productVariantId
                        isShippingRequired
                        quantity
                        quantityFulfilled
                        unitPrice {
                            gross {
                                amount
                            }
                            net {
                                amount
                            }
                        }
                        undiscountedUnitPrice{
                            gross {
                                amount
                            }
                            net {
                                amount
                            }
                        }
                        taxClass {
                            id
                        }
                        taxClassName
                    }
                    billingAddress{
                        postalCode
                    }
                    shippingAddress{
                        postalCode
                    }
                    shippingMethods {
                        id
                    }
                    shippingMethodName
                    shippingTaxClass{
                        name
                    }
                    shippingTaxClassName
                    shippingPrice {
                        gross {
                            amount
                        }
                        net {
                            amount
                        }
                    }
                    total{
                        gross {
                            amount
                        }
                        net {
                            amount
                        }
                    }
                    undiscountedTotal{
                        gross {
                            amount
                        }
                        net {
                            amount
                        }
                    }

                    events {
                        message
                        user {
                            id
                        }
                        app {
                            id
                        }
                    }
                    weight {
                        value
                    }
                    externalReference
                    trackingClientId
                    displayGrossPrices
                    channel {
                        slug
                    }
                    status
                    created
                    languageCode
                    collectionPointName
                    redirectUrl
                    origin
                    fulfillments {
                        lines {
                            quantity
                            orderLine {
                                id
                            }
                        }
                    }
                }
                errors {
                    field
                    message
                    code
                }
            }
        }
    }
"""


@pytest.fixture
def order_bulk_input(
    app,
    channel_PLN,
    customer_user,
    default_tax_class,
    graphql_address_data,
    shipping_method_channel_PLN,
    variant,
):
    shipping_method = shipping_method_channel_PLN
    user = {
        "id": graphene.Node.to_global_id("User", customer_user.id),
        "email": None,
    }
    delivery_method = {
        "shippingMethodId": graphene.Node.to_global_id(
            "ShippingMethod", shipping_method.id
        ),
        "shippingTaxClassId": graphene.Node.to_global_id(
            "TaxClass", default_tax_class.id
        ),
        "shippingPrice": {
            "gross": 120,
            "net": 100,
        },
        "shippingTaxRate": 0.2,
    }
    line = {
        "variantId": graphene.Node.to_global_id("ProductVariant", variant.id),
        "createdAt": timezone.now(),
        "productName": "Product Name",
        "variantName": "Variant Name",
        "translatedProductName": "Nazwa Produktu",
        "translatedVariantName": "Nazwa Wariantu",
        "isShippingRequired": True,
        "isGiftCard": False,
        "quantity": 5,
        "quantityFulfilled": 0,
        "totalPrice": {
            "gross": 120,
            "net": 100,
        },
        "undiscountedTotalPrice": {
            "gross": 120,
            "net": 100,
        },
        "taxRate": 0.2,
        "taxClassId": graphene.Node.to_global_id("TaxClass", default_tax_class.id),
        "taxClassName": "Line Tax Class Name",
    }
    note = {
        "message": "Test message",
        "date": timezone.now(),
        "userId": graphene.Node.to_global_id("User", customer_user.id),
    }
    return {
        "channel": channel_PLN.slug,
        "createdAt": timezone.now(),
        "status": OrderStatus.DRAFT,
        "user": user,
        "billingAddress": graphql_address_data,
        "shippingAddress": graphql_address_data,
        "currency": "PLN",
        "languageCode": "PL",
        "deliveryMethod": delivery_method,
        "lines": [line],
        "notes": [note],
        "weight": "10.15",
        "trackingClientId": "tracking-id-123",
        "redirectUrl": "https://www.example.com",
    }


def test_order_bulk_create(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
    app,
    channel_PLN,
    customer_user,
    default_tax_class,
    graphql_address_data,
    shipping_method_channel_PLN,
    variant,
):
    # given
    orders_count = Order.objects.count()
    order_lines_count = OrderLine.objects.count()
    order_events_count = OrderEvent.objects.count()
    address_count = Address.objects.count()

    order = order_bulk_input
    order["externalReference"] = "ext-ref-1"

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 1
    data = content["data"]["orderBulkCreate"]["results"]
    assert not data[0]["errors"]

    order = data[0]["order"]
    assert order["externalReference"] == "ext-ref-1"
    assert order["channel"]["slug"] == channel_PLN.slug
    assert order["created"]
    assert order["status"] == OrderStatus.DRAFT.upper()
    assert order["user"]["id"] == graphene.Node.to_global_id("User", customer_user.id)
    assert order["languageCode"] == "pl"
    assert not order["collectionPointName"]
    assert order["shippingMethodName"] == shipping_method_channel_PLN.name
    assert order["shippingTaxClassName"] == default_tax_class.name
    assert order["shippingPrice"]["gross"]["amount"] == 120
    assert order["shippingPrice"]["net"]["amount"] == 100
    assert order["total"]["gross"]["amount"] == 120
    assert order["total"]["net"]["amount"] == 100
    assert order["undiscountedTotal"]["gross"]["amount"] == 120
    assert order["undiscountedTotal"]["net"]["amount"] == 100
    assert order["redirectUrl"] == "https://www.example.com"
    assert order["origin"] == OrderOrigin.BULK_CREATE.upper()
    assert order["weight"]["value"] == 10.15
    assert order["trackingClientId"] == "tracking-id-123"
    assert order["displayGrossPrices"]
    db_order = Order.objects.get()
    assert db_order.external_reference == "ext-ref-1"
    assert db_order.channel.slug == channel_PLN.slug
    assert db_order.created_at
    assert db_order.status == OrderStatus.DRAFT
    assert db_order.user == customer_user
    assert db_order.language_code == "pl"
    assert not db_order.collection_point
    assert not db_order.collection_point_name
    assert db_order.shipping_method == shipping_method_channel_PLN
    assert db_order.shipping_method_name == shipping_method_channel_PLN.name
    assert db_order.shipping_tax_class == default_tax_class
    assert db_order.shipping_tax_class_name == default_tax_class.name
    assert db_order.shipping_tax_rate == 0.2
    assert db_order.shipping_price_gross_amount == 120
    assert db_order.shipping_price_net_amount == 100
    assert db_order.total_gross_amount == 120
    assert db_order.total_net_amount == 100
    assert db_order.undiscounted_total_gross_amount == 120
    assert db_order.undiscounted_total_net_amount == 100
    assert db_order.redirect_url == "https://www.example.com"
    assert db_order.origin == OrderOrigin.BULK_CREATE
    assert db_order.weight.g == 10.15 * 1000
    assert db_order.tracking_client_id == "tracking-id-123"
    assert db_order.display_gross_prices
    assert db_order.currency == "PLN"

    line = order["lines"][0]
    assert line["variant"]["id"] == graphene.Node.to_global_id(
        "ProductVariant", variant.id
    )
    assert line["productName"] == "Product Name"
    assert line["variantName"] == "Variant Name"
    assert line["translatedProductName"] == "Nazwa Produktu"
    assert line["translatedVariantName"] == "Nazwa Wariantu"
    assert line["isShippingRequired"]
    assert line["quantity"] == 5
    assert line["quantityFulfilled"] == 0
    assert line["unitPrice"]["gross"]["amount"] == Decimal(120 / 5)
    assert line["unitPrice"]["net"]["amount"] == Decimal(100 / 5)
    assert line["taxClass"]["id"] == graphene.Node.to_global_id(
        "TaxClass", default_tax_class.id
    )
    assert line["taxClassName"] == "Line Tax Class Name"
    db_line = OrderLine.objects.get()
    assert db_line.variant == variant
    assert db_line.product_name == "Product Name"
    assert db_line.variant_name == "Variant Name"
    assert db_line.translated_product_name == "Nazwa Produktu"
    assert db_line.translated_variant_name == "Nazwa Wariantu"
    assert db_line.is_shipping_required
    assert db_line.quantity == 5
    assert db_line.quantity_fulfilled == 0
    assert db_line.unit_price.gross.amount == Decimal(120 / 5)
    assert db_line.unit_price.net.amount == Decimal(100 / 5)
    assert db_line.tax_class == default_tax_class
    assert db_line.tax_class_name == "Line Tax Class Name"
    assert db_line.currency == "PLN"
    assert db_order.lines.first() == db_line

    assert order["billingAddress"]["postalCode"] == graphql_address_data["postalCode"]
    assert order["shippingAddress"]["postalCode"] == graphql_address_data["postalCode"]
    assert db_order.billing_address.postal_code == graphql_address_data["postalCode"]
    assert db_order.shipping_address.postal_code == graphql_address_data["postalCode"]

    note = order["events"][0]
    assert note["message"] == "Test message"
    assert note["user"]["id"] == graphene.Node.to_global_id("User", customer_user.id)
    assert not note["app"]
    db_event = OrderEvent.objects.get()
    assert db_event.parameters["message"] == "Test message"
    assert db_event.user == customer_user
    assert not db_event.app
    assert db_order.events.first() == db_event

    assert Order.objects.count() == orders_count + 1
    assert OrderLine.objects.count() == order_lines_count + 1
    assert Address.objects.count() == address_count + 2
    assert OrderEvent.objects.count() == order_events_count + 1


def test_order_bulk_create_multiple_orders(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()
    order_lines_count = OrderLine.objects.count()

    order_1 = order_bulk_input
    order_2 = order_bulk_input

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order_1, order_2]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 2
    data = content["data"]["orderBulkCreate"]["results"]
    assert not data[0]["errors"]
    assert not data[1]["errors"]
    order_1 = data[0]["order"]
    order_2 = data[1]["order"]

    assert order_1["lines"]
    assert order_2["lines"]
    assert Order.objects.count() == orders_count + 2
    assert OrderLine.objects.count() == order_lines_count + 2


@pytest.mark.parametrize(
    "error_policy,expected_order_count",
    [
        (ErrorPolicyEnum.REJECT_EVERYTHING.name, 0),
        (ErrorPolicyEnum.REJECT_FAILED_ROWS.name, 1),
        (ErrorPolicyEnum.IGNORE_FAILED.name, 2),
    ],
)
def test_order_bulk_create_error_policy(
    error_policy,
    expected_order_count,
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
    app,
):
    # given
    orders_count = Order.objects.count()

    order_1 = order_bulk_input
    order_2 = copy.deepcopy(order_bulk_input)
    order_2["notes"][0]["appId"] = graphene.Node.to_global_id("App", app.id)

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {
        "errorPolicy": error_policy,
        "orders": [order_1, order_2],
    }

    # when
    staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)

    # then
    assert Order.objects.count() == orders_count + expected_order_count


def test_order_bulk_create_error_negative_weight(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["weight"] = -5

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 0
    assert not content["data"]["orderBulkCreate"]["results"][0]["order"]
    error = content["data"]["orderBulkCreate"]["results"][0]["errors"][0]
    assert error["message"] == "Product can't have negative weight."
    assert error["field"] == "weight"
    assert error["code"] == OrderBulkCreateErrorCode.INVALID.name

    assert Order.objects.count() == orders_count


def test_order_bulk_create_error_future_date(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["createdAt"] = timezone.now() + timedelta(minutes=MINUTES_DIFF + 1)

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 0
    assert not content["data"]["orderBulkCreate"]["results"][0]["order"]
    error = content["data"]["orderBulkCreate"]["results"][0]["errors"][0]
    assert error["message"] == "Order input contains future date."
    assert error["field"] == "createdAt"
    assert error["code"] == OrderBulkCreateErrorCode.INVALID.name

    assert Order.objects.count() == orders_count


def test_order_bulk_create_error_invalid_redirect_url(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["redirectUrl"] = "www.invalid-url.com"

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 0
    assert not content["data"]["orderBulkCreate"]["results"][0]["order"]
    error = content["data"]["orderBulkCreate"]["results"][0]["errors"][0]
    assert (
        error["message"] == "Invalid redirect url: Invalid URL. "
        "Please check if URL is in RFC 1808 format.."
    )
    assert error["field"] == "redirectUrl"
    assert error["code"] == OrderBulkCreateErrorCode.INVALID.name

    assert Order.objects.count() == orders_count


def test_order_bulk_create_error_invalid_address(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["billingAddress"] = {"firstName": "John"}
    order["shippingAddress"] = {"postalCode": "abc-123"}

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 0
    assert not content["data"]["orderBulkCreate"]["results"][0]["order"]
    error_1 = content["data"]["orderBulkCreate"]["results"][0]["errors"][0]
    assert error_1["message"] == "Invalid billing address."
    assert error_1["field"] == "billingAddress"
    assert error_1["code"] == OrderBulkCreateErrorCode.INVALID.name

    error_2 = content["data"]["orderBulkCreate"]["results"][0]["errors"][1]
    assert error_2["message"] == "Invalid shipping address."
    assert error_2["field"] == "shippingAddress"
    assert error_2["code"] == OrderBulkCreateErrorCode.INVALID.name

    assert Order.objects.count() == orders_count


def test_order_bulk_create_order_calculations(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    assert True


def test_order_bulk_create_no_shipping_method_price(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["deliveryMethod"]["shippingPrice"] = None

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 1
    order = content["data"]["orderBulkCreate"]["results"][0]["order"]
    assert not content["data"]["orderBulkCreate"]["results"][0]["errors"]

    assert Order.objects.count() == orders_count + 1


def test_order_bulk_create_error_delivery_with_both_shipping_method_and_warehouse(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
    warehouse,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["deliveryMethod"]["warehouseId"] = graphene.Node.to_global_id(
        "Warehouse", warehouse.id
    )

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 0
    assert not content["data"]["orderBulkCreate"]["results"][0]["order"]
    error = content["data"]["orderBulkCreate"]["results"][0]["errors"][0]
    assert (
        error["message"] == "Can't provide both warehouse and shipping method IDs"
        " in deliveryMethod field."
    )
    assert error["field"] == "deliveryMethod"
    assert error["code"] == OrderBulkCreateErrorCode.INVALID.name

    assert Order.objects.count() == orders_count


def test_order_bulk_create_warehouse_delivery_method(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
    warehouse,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["deliveryMethod"]["warehouseId"] = graphene.Node.to_global_id(
        "Warehouse", warehouse.id
    )
    order["deliveryMethod"]["shippingMethodId"] = None

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 1
    assert not content["data"]["orderBulkCreate"]["results"][0]["errors"]
    order = content["data"]["orderBulkCreate"]["results"][0]["order"]
    assert order["collectionPointName"] == warehouse.name
    assert not order["shippingMethodName"]

    db_order = Order.objects.get()
    assert db_order.collection_point == warehouse
    assert db_order.collection_point_name == warehouse.name
    assert not db_order.shipping_method
    assert not db_order.shipping_method_name

    assert Order.objects.count() == orders_count + 1


def test_order_bulk_create_error_no_delivery_method_provided(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["deliveryMethod"]["shippingMethodId"] = None

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 0
    assert not content["data"]["orderBulkCreate"]["results"][0]["order"]
    error = content["data"]["orderBulkCreate"]["results"][0]["errors"][0]
    assert error["message"] == "No delivery method provided."
    assert error["field"] == "deliveryMethod"
    assert error["code"] == OrderBulkCreateErrorCode.INVALID.name

    assert Order.objects.count() == orders_count


def test_order_bulk_create_error_note_with_future_date(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["notes"][0]["date"] = timezone.now() + timedelta(minutes=MINUTES_DIFF + 1)

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 0
    assert not content["data"]["orderBulkCreate"]["results"][0]["order"]
    error = content["data"]["orderBulkCreate"]["results"][0]["errors"][0]
    assert error["message"] == "Note input contains future date."
    assert error["field"] == "date"
    assert error["code"] == OrderBulkCreateErrorCode.INVALID.name

    assert Order.objects.count() == orders_count


def test_order_bulk_create_error_non_existing_variant(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["lines"][0]["variantId"] = None
    order["lines"][0]["variantSku"] = "non-existing-sku"

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 0
    assert not content["data"]["orderBulkCreate"]["results"][0]["order"]
    errors = content["data"]["orderBulkCreate"]["results"][0]["errors"]

    assert errors[0]["message"] == "At least one order line can't be created."
    assert errors[0]["field"] == "lines"
    assert errors[0]["code"] == OrderBulkCreateErrorCode.INVALID.name

    assert (
        errors[1]["message"]
        == "ProductVariant instance with sku=non-existing-sku doesn't exist."
    )
    assert not errors[1]["field"]
    assert not errors[1]["code"]

    assert Order.objects.count() == orders_count


def test_order_bulk_create_error_user_not_found(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["user"]["email"] = "non-existing-user@example.com"
    order["user"]["id"] = None

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 0
    assert not content["data"]["orderBulkCreate"]["results"][0]["order"]
    error = content["data"]["orderBulkCreate"]["results"][0]["errors"][0]
    assert (
        error["message"]
        == "User instance with email=non-existing-user@example.com doesn't exist."
    )
    assert not error["field"]
    assert not error["code"]

    assert Order.objects.count() == orders_count


def test_order_bulk_create_error_get_instance_with_multiple_keys(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["user"]["email"] = "non-existing-user@example.com"

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 0
    assert not content["data"]["orderBulkCreate"]["results"][0]["order"]
    error = content["data"]["orderBulkCreate"]["results"][0]["errors"][0]
    assert (
        error["message"] == "Only one of [id, email, external_reference] arguments"
        " can be provided to resolve User instance."
    )
    assert not error["field"]
    assert not error["code"]

    assert Order.objects.count() == orders_count


def test_order_bulk_create_error_get_instance_with_no_keys(
    staff_api_client,
    permission_manage_orders,
    order_bulk_input,
):
    # given
    orders_count = Order.objects.count()

    order = order_bulk_input
    order["user"]["id"] = None

    staff_api_client.user.user_permissions.add(permission_manage_orders)
    variables = {"orders": [order]}

    # when
    response = staff_api_client.post_graphql(ORDER_BULK_CREATE, variables)
    content = get_graphql_content(response)

    # then
    assert content["data"]["orderBulkCreate"]["count"] == 0
    assert not content["data"]["orderBulkCreate"]["results"][0]["order"]
    error = content["data"]["orderBulkCreate"]["results"][0]["errors"][0]
    assert (
        error["message"] == "One of [id, email, external_reference] arguments"
        " must be provided to resolve User instance."
    )
    assert not error["field"]
    assert not error["code"]

    assert Order.objects.count() == orders_count
