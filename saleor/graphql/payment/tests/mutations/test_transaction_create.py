from decimal import Decimal

import graphene
import pytest

from .....order import OrderEvents
from .....order.utils import update_order_authorize_data, update_order_charge_data
from .....payment import TransactionEventStatus
from .....payment.error_codes import TransactionCreateErrorCode
from .....payment.models import TransactionEvent, TransactionItem
from .....tests.consts import TEST_SERVER_DOMAIN
from ....tests.utils import assert_no_permission, get_graphql_content
from ...enums import (
    TransactionActionEnum,
    TransactionEventActionTypeEnum,
    TransactionEventStatusEnum,
)

MUTATION_TRANSACTION_CREATE = """
mutation TransactionCreate(
    $id: ID!,
    $transaction_event: TransactionEventInput,
    $transaction: TransactionCreateInput!
    ){
    transactionCreate(
            id: $id,
            transactionEvent: $transaction_event,
            transaction: $transaction
        ){
        transaction{
                id
                actions
                pspReference
                type
                status
                modifiedAt
                createdAt
                externalUrl
                authorizedAmount{
                    amount
                    currency
                }
                voidedAmount{
                    currency
                    amount
                }
                chargedAmount{
                    currency
                    amount
                }
                refundedAmount{
                    currency
                    amount
                }
                events{
                    status
                    pspReference
                    name
                    createdAt
                    externalUrl
                    amount{
                        amount
                        currency
                    }
                    type
                }
        }
        errors{
            field
            message
            code
        }
    }
}
"""


def test_transaction_create_for_order_by_app(
    order_with_lines, permission_manage_payments, app_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}
    external_url = f"http://{TEST_SERVER_DOMAIN}.com/external-url"
    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
            "externalUrl": external_url,
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = order_with_lines.payment_transactions.first()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]
    assert data["actions"] == available_actions
    assert data["status"] == status
    assert data["pspReference"] == psp_reference
    assert data["authorizedAmount"]["amount"] == authorized_value
    assert data["externalUrl"] == external_url

    assert available_actions == list(map(str.upper, transaction.available_actions))
    assert status == transaction.status
    assert psp_reference == transaction.psp_reference
    assert authorized_value == transaction.authorized_value
    assert transaction.metadata == {metadata["key"]: metadata["value"]}
    assert transaction.private_metadata == {
        private_metadata["key"]: private_metadata["value"]
    }
    assert transaction.app == app_api_client.app
    assert transaction.external_url == external_url


def test_transaction_create_for_order_updates_order_total_authorized_by_app(
    order_with_lines, permission_manage_payments, app_api_client
):
    # given
    previously_authorized_value = Decimal("90")
    old_transaction = order_with_lines.payment_transactions.create(
        authorized_value=previously_authorized_value, currency=order_with_lines.currency
    )

    update_order_authorize_data(order_with_lines)

    authorized_value = Decimal("10")

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": "Authorized for 10$",
            "type": "Credit Card",
            "pspReference": "PSP reference - 123",
            "availableActions": [],
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    order_with_lines.refresh_from_db()
    transaction = order_with_lines.payment_transactions.exclude(
        id=old_transaction.id
    ).last()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]
    assert data["authorizedAmount"]["amount"] == authorized_value
    assert (
        order_with_lines.total_authorized_amount
        == previously_authorized_value + authorized_value
    )
    assert authorized_value == transaction.authorized_value


def test_transaction_create_for_order_updates_order_total_charged_by_app(
    order_with_lines, permission_manage_payments, app_api_client
):
    # given
    previously_charged_value = Decimal("90")
    old_transaction = order_with_lines.payment_transactions.create(
        charged_value=previously_charged_value, currency=order_with_lines.currency
    )
    update_order_charge_data(order_with_lines)

    charged_value = Decimal("10")

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": "Charged 10$",
            "type": "Credit Card",
            "pspReference": "PSP reference - 123",
            "availableActions": [],
            "amountCharged": {
                "amount": charged_value,
                "currency": "USD",
            },
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    order_with_lines.refresh_from_db()
    transaction = order_with_lines.payment_transactions.exclude(
        id=old_transaction.id
    ).last()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]
    assert data["chargedAmount"]["amount"] == charged_value
    assert (
        order_with_lines.total_charged_amount
        == previously_charged_value + charged_value
    )
    assert charged_value == transaction.charged_value


def test_transaction_create_for_checkout_by_app(
    checkout_with_items, permission_manage_payments, app_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    variables = {
        "id": graphene.Node.to_global_id("Checkout", checkout_with_items.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = checkout_with_items.payment_transactions.first()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]
    assert data["actions"] == available_actions
    assert data["status"] == status
    assert data["pspReference"] == psp_reference
    assert data["authorizedAmount"]["amount"] == authorized_value

    assert available_actions == list(map(str.upper, transaction.available_actions))
    assert status == transaction.status
    assert psp_reference == transaction.psp_reference
    assert authorized_value == transaction.authorized_value
    assert transaction.metadata == {metadata["key"]: metadata["value"]}
    assert transaction.private_metadata == {
        private_metadata["key"]: private_metadata["value"]
    }


@pytest.mark.parametrize(
    "amount_field_name, amount_db_field",
    [
        ("amountAuthorized", "authorized_value"),
        ("amountCharged", "charged_value"),
        ("amountVoided", "voided_value"),
        ("amountRefunded", "refunded_value"),
    ],
)
def test_transaction_create_calculate_amount_by_app(
    amount_field_name,
    amount_db_field,
    order_with_lines,
    permission_manage_payments,
    app_api_client,
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    expected_value = Decimal("10")

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": [],
            amount_field_name: {
                "amount": expected_value,
                "currency": "USD",
            },
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = TransactionItem.objects.first()
    get_graphql_content(response)

    assert getattr(transaction, amount_db_field) == expected_value


def test_transaction_create_multiple_amounts_provided_by_app(
    order_with_lines, permission_manage_payments, app_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    charged_value = Decimal("11")
    refunded_value = Decimal("12")
    voided_value = Decimal("13")

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "amountCharged": {
                "amount": charged_value,
                "currency": "USD",
            },
            "amountRefunded": {
                "amount": refunded_value,
                "currency": "USD",
            },
            "amountVoided": {
                "amount": voided_value,
                "currency": "USD",
            },
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = TransactionItem.objects.first()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]
    assert data["actions"] == available_actions
    assert data["status"] == status
    assert data["pspReference"] == psp_reference
    assert data["authorizedAmount"]["amount"] == authorized_value
    assert data["chargedAmount"]["amount"] == charged_value
    assert data["refundedAmount"]["amount"] == refunded_value
    assert data["voidedAmount"]["amount"] == voided_value

    assert transaction.authorized_value == authorized_value
    assert transaction.charged_value == charged_value
    assert transaction.voided_value == voided_value
    assert transaction.refunded_value == refunded_value


def test_transaction_create_create_event_for_order_by_app(
    order_with_lines, permission_manage_payments, app_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    transaction_status = "PENDING"
    transaction_reference = "transaction reference"
    transaction_name = "Processing transaction"

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
        },
        "transaction_event": {
            "status": transaction_status,
            "pspReference": transaction_reference,
            "name": transaction_name,
        },
    }

    # when
    app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    event = order_with_lines.events.first()

    assert event.type == OrderEvents.TRANSACTION_EVENT
    assert event.parameters == {
        "message": transaction_name,
        "reference": transaction_reference,
        "status": transaction_status.lower(),
    }


def test_transaction_create_missing_permission_by_app(order_with_lines, app_api_client):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
    }

    # when
    response = app_api_client.post_graphql(MUTATION_TRANSACTION_CREATE, variables)

    # then
    assert_no_permission(response)


@pytest.mark.parametrize(
    "amount_field_name, amount_db_field",
    [
        ("amountAuthorized", "authorized_value"),
        ("amountCharged", "charged_value"),
        ("amountVoided", "voided_value"),
        ("amountRefunded", "refunded_value"),
    ],
)
def test_transaction_create_incorrect_currency_by_app(
    amount_field_name,
    amount_db_field,
    order_with_lines,
    permission_manage_payments,
    app_api_client,
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    expected_value = Decimal("10")

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": [],
            amount_field_name: {
                "amount": expected_value,
                "currency": "PLN",
            },
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]
    assert data["errors"][0]["field"] == amount_field_name
    assert (
        data["errors"][0]["code"] == TransactionCreateErrorCode.INCORRECT_CURRENCY.name
    )


def test_transaction_create_empty_metadata_key_by_app(
    order_with_lines, permission_manage_payments, app_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}
    external_url = f"http://{TEST_SERVER_DOMAIN}.com/external-url"
    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
            "externalUrl": external_url,
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    content = get_graphql_content(response, ignore_errors=True)
    assert not content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.METADATA_KEY_REQUIRED.name


def test_transaction_create_empty_private_metadata_key_by_app(
    order_with_lines, permission_manage_payments, app_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "", "value": "321"}
    external_url = f"http://{TEST_SERVER_DOMAIN}.com/external-url"
    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
            "externalUrl": external_url,
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    content = get_graphql_content(response, ignore_errors=True)
    assert not content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.METADATA_KEY_REQUIRED.name


def test_transaction_create_external_url_incorrect_url_format_by_app(
    order_with_lines, permission_manage_payments, app_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test", "value": "321"}
    external_url = "incorrect"
    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
            "externalUrl": external_url,
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    content = get_graphql_content(response, ignore_errors=True)
    assert not content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.INVALID.name


def test_creates_transaction_event_incorrect_external_url_by_app(
    order_with_lines, permission_manage_payments, app_api_client
):
    # given
    status = "Failed authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = []
    authorized_value = Decimal("0")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    event_psp_reference = "PSP-ref"
    event_name = "Failed authorization"
    external_url = "incorrect"
    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
        "transaction_event": {
            "status": TransactionEventStatusEnum.FAILURE.name,
            "pspReference": event_psp_reference,
            "name": event_name,
            "externalUrl": external_url,
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    content = get_graphql_content(response, ignore_errors=True)
    assert not content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.INVALID.name


def test_creates_transaction_event_for_order_by_app(
    order_with_lines, permission_manage_payments, app_api_client
):
    # given
    status = "Failed authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = []
    authorized_value = Decimal("0")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    event_status = TransactionEventStatus.FAILURE
    event_psp_reference = "PSP-ref"
    event_name = "Failed authorization"
    external_url = f"http://{TEST_SERVER_DOMAIN}.com/external-url"

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
        "transaction_event": {
            "status": TransactionEventStatusEnum.FAILURE.name,
            "pspReference": event_psp_reference,
            "name": event_name,
            "externalUrl": external_url,
            "amount": authorized_value,
            "type": TransactionEventActionTypeEnum.AUTHORIZE.name,
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = order_with_lines.payment_transactions.first()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]

    events_data = data["events"]
    assert len(events_data) == 1
    event_data = events_data[0]
    assert event_data["name"] == event_name
    assert event_data["status"] == TransactionEventStatusEnum.FAILURE.name
    assert event_data["pspReference"] == event_psp_reference
    assert event_data["externalUrl"] == external_url
    assert event_data["amount"]["currency"] == transaction.currency
    assert event_data["amount"]["amount"] == authorized_value
    assert event_data["type"] == TransactionEventActionTypeEnum.AUTHORIZE.name

    assert transaction.events.count() == 1
    event = transaction.events.first()
    assert event.name == event_name
    assert event.status == event_status
    assert event.psp_reference == event_psp_reference
    assert event.external_url == external_url
    assert event.amount_value == authorized_value
    assert event.currency == transaction.currency
    assert event.type == TransactionEventActionTypeEnum.AUTHORIZE.value


def test_creates_transaction_event_for_checkout_by_app(
    checkout_with_items, permission_manage_payments, app_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    event_status = TransactionEventStatus.FAILURE
    event_psp_reference = "PSP-ref"
    event_name = "Failed authorization"
    external_url = f"http://{TEST_SERVER_DOMAIN}.com/external-url"

    variables = {
        "id": graphene.Node.to_global_id("Checkout", checkout_with_items.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
        "transaction_event": {
            "status": TransactionEventStatusEnum.FAILURE.name,
            "pspReference": event_psp_reference,
            "name": event_name,
            "externalUrl": external_url,
            "amount": authorized_value,
            "type": TransactionEventActionTypeEnum.AUTHORIZE.name,
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = checkout_with_items.payment_transactions.first()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]

    events_data = data["events"]
    assert len(events_data) == 1
    event_data = events_data[0]
    assert event_data["name"] == event_name
    assert event_data["status"] == TransactionEventStatusEnum.FAILURE.name
    assert event_data["pspReference"] == event_psp_reference
    assert event_data["externalUrl"] == external_url
    assert event_data["amount"]["currency"] == transaction.currency
    assert event_data["amount"]["amount"] == authorized_value
    assert event_data["type"] == TransactionEventActionTypeEnum.AUTHORIZE.name

    assert transaction.events.count() == 1
    event = transaction.events.first()
    assert event.name == event_name
    assert event.status == event_status
    assert event.psp_reference == event_psp_reference
    assert event.external_url == external_url
    assert event.amount_value == authorized_value
    assert event.currency == transaction.currency
    assert event.type == TransactionEventActionTypeEnum.AUTHORIZE.value


def test_creates_transaction_error_when_psp_reference_already_exists_by_app(
    checkout_with_items,
    permission_manage_payments,
    app_api_client,
    transaction_item_created_by_user,
):
    # given
    transaction_item_created_by_user.checkout = checkout_with_items
    transaction_item_created_by_user.order = None
    transaction_item_created_by_user.save()

    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = transaction_item_created_by_user.psp_reference
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    event_psp_reference = "PSP-ref"
    event_name = "Failed authorization"

    variables = {
        "id": graphene.Node.to_global_id("Checkout", checkout_with_items.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
        "transaction_event": {
            "status": TransactionEventStatusEnum.FAILURE.name,
            "pspReference": event_psp_reference,
            "name": event_name,
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then

    content = get_graphql_content(response, ignore_errors=True)
    transaction = content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]

    assert not transaction
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.UNIQUE.name
    assert error["field"] == "transaction"
    assert checkout_with_items.payment_transactions.count() == 1
    assert TransactionEvent.objects.count() == 0


def test_creates_transaction_error_when_event_psp_reference_already_exists_by_app(
    checkout_with_items,
    permission_manage_payments,
    app_api_client,
    transaction_item_created_by_user,
):
    # given
    transaction_item_created_by_user.checkout = checkout_with_items
    transaction_item_created_by_user.order = None
    transaction_item_created_by_user.save()

    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP-ref"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    event_psp_reference = "PSP-ref"
    event_name = "Failed authorization"
    transaction_item_created_by_user.events.create(psp_reference=event_psp_reference)

    variables = {
        "id": graphene.Node.to_global_id("Checkout", checkout_with_items.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
        "transaction_event": {
            "status": TransactionEventStatusEnum.FAILURE.name,
            "pspReference": event_psp_reference,
            "name": event_name,
        },
    }

    # when
    response = app_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = checkout_with_items.payment_transactions.first()
    content = get_graphql_content(response, ignore_errors=True)
    transaction = content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]

    assert not transaction
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.UNIQUE.name
    assert error["field"] == "transactionEvent"
    assert checkout_with_items.payment_transactions.count() == 1
    assert TransactionEvent.objects.count() == 1


def test_creates_transaction_error_when_event_psp_reference_already_exists_by_staff(
    checkout_with_items,
    permission_manage_payments,
    staff_api_client,
    transaction_item_created_by_user,
):
    # given
    transaction_item_created_by_user.checkout = checkout_with_items
    transaction_item_created_by_user.order = None
    transaction_item_created_by_user.save()

    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP-ref"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    event_psp_reference = "PSP-ref"
    event_name = "Failed authorization"
    transaction_item_created_by_user.events.create(psp_reference=event_psp_reference)

    variables = {
        "id": graphene.Node.to_global_id("Checkout", checkout_with_items.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
        "transaction_event": {
            "status": TransactionEventStatusEnum.FAILURE.name,
            "pspReference": event_psp_reference,
            "name": event_name,
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = checkout_with_items.payment_transactions.first()
    content = get_graphql_content(response, ignore_errors=True)
    transaction = content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]

    assert not transaction
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.UNIQUE.name
    assert error["field"] == "transactionEvent"
    assert checkout_with_items.payment_transactions.count() == 1
    assert TransactionEvent.objects.count() == 1


def test_creates_transaction_error_when_psp_reference_already_exists_by_staff(
    checkout_with_items,
    permission_manage_payments,
    staff_api_client,
    transaction_item_created_by_user,
):
    # given
    transaction_item_created_by_user.checkout = checkout_with_items
    transaction_item_created_by_user.order = None
    transaction_item_created_by_user.save()

    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = transaction_item_created_by_user.psp_reference
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    event_psp_reference = "PSP-ref"
    event_name = "Failed authorization"

    variables = {
        "id": graphene.Node.to_global_id("Checkout", checkout_with_items.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
        "transaction_event": {
            "status": TransactionEventStatusEnum.FAILURE.name,
            "pspReference": event_psp_reference,
            "name": event_name,
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    content = get_graphql_content(response, ignore_errors=True)
    transaction = content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]

    assert not transaction
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.UNIQUE.name
    assert error["field"] == "transaction"

    assert checkout_with_items.payment_transactions.count() == 1
    assert TransactionEvent.objects.count() == 0


def test_transaction_create_for_order_by_staff(
    order_with_lines, permission_manage_payments, staff_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}
    external_url = f"http://{TEST_SERVER_DOMAIN}.com/external-url"

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
            "externalUrl": external_url,
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = order_with_lines.payment_transactions.first()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]
    assert data["actions"] == available_actions
    assert data["status"] == status
    assert data["pspReference"] == psp_reference
    assert data["authorizedAmount"]["amount"] == authorized_value
    assert data["externalUrl"] == external_url

    assert available_actions == list(map(str.upper, transaction.available_actions))
    assert status == transaction.status
    assert psp_reference == transaction.psp_reference
    assert authorized_value == transaction.authorized_value
    assert transaction.metadata == {metadata["key"]: metadata["value"]}
    assert transaction.private_metadata == {
        private_metadata["key"]: private_metadata["value"]
    }
    assert transaction.external_url == external_url
    assert transaction.user == staff_api_client.user
    assert not transaction.app


def test_transaction_create_for_order_updates_order_total_authorized_by_staff(
    order_with_lines, permission_manage_payments, staff_api_client
):
    # given
    previously_authorized_value = Decimal("90")
    old_transaction = order_with_lines.payment_transactions.create(
        authorized_value=previously_authorized_value, currency=order_with_lines.currency
    )

    update_order_authorize_data(order_with_lines)

    authorized_value = Decimal("10")

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": "Authorized for 10$",
            "type": "Credit Card",
            "pspReference": "PSP reference - 123",
            "availableActions": [],
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    order_with_lines.refresh_from_db()
    transaction = order_with_lines.payment_transactions.exclude(
        id=old_transaction.id
    ).last()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]
    assert data["authorizedAmount"]["amount"] == authorized_value
    assert (
        order_with_lines.total_authorized_amount
        == previously_authorized_value + authorized_value
    )
    assert authorized_value == transaction.authorized_value


def test_transaction_create_for_order_updates_order_total_charged_by_staff(
    order_with_lines, permission_manage_payments, staff_api_client
):
    # given
    previously_charged_value = Decimal("90")
    old_transaction = order_with_lines.payment_transactions.create(
        charged_value=previously_charged_value, currency=order_with_lines.currency
    )
    update_order_charge_data(order_with_lines)

    charged_value = Decimal("10")

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": "Charged 10$",
            "type": "Credit Card",
            "pspReference": "PSP reference - 123",
            "availableActions": [],
            "amountCharged": {
                "amount": charged_value,
                "currency": "USD",
            },
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    order_with_lines.refresh_from_db()
    transaction = order_with_lines.payment_transactions.exclude(
        id=old_transaction.id
    ).last()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]
    assert data["chargedAmount"]["amount"] == charged_value
    assert (
        order_with_lines.total_charged_amount
        == previously_charged_value + charged_value
    )
    assert charged_value == transaction.charged_value


def test_transaction_create_for_checkout_by_staff(
    checkout_with_items, permission_manage_payments, staff_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    variables = {
        "id": graphene.Node.to_global_id("Checkout", checkout_with_items.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = checkout_with_items.payment_transactions.first()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]
    assert data["actions"] == available_actions
    assert data["status"] == status
    assert data["pspReference"] == psp_reference
    assert data["authorizedAmount"]["amount"] == authorized_value

    assert available_actions == list(map(str.upper, transaction.available_actions))
    assert status == transaction.status
    assert psp_reference == transaction.psp_reference
    assert authorized_value == transaction.authorized_value
    assert transaction.metadata == {metadata["key"]: metadata["value"]}
    assert transaction.private_metadata == {
        private_metadata["key"]: private_metadata["value"]
    }


@pytest.mark.parametrize(
    "amount_field_name, amount_db_field",
    [
        ("amountAuthorized", "authorized_value"),
        ("amountCharged", "charged_value"),
        ("amountVoided", "voided_value"),
        ("amountRefunded", "refunded_value"),
    ],
)
def test_transaction_create_calculate_amount_by_staff(
    amount_field_name,
    amount_db_field,
    order_with_lines,
    permission_manage_payments,
    staff_api_client,
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    expected_value = Decimal("10")

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": [],
            amount_field_name: {
                "amount": expected_value,
                "currency": "USD",
            },
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = TransactionItem.objects.first()
    get_graphql_content(response)

    assert getattr(transaction, amount_db_field) == expected_value


def test_transaction_create_multiple_amounts_provided_by_staff(
    order_with_lines, permission_manage_payments, staff_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    charged_value = Decimal("11")
    refunded_value = Decimal("12")
    voided_value = Decimal("13")

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "amountCharged": {
                "amount": charged_value,
                "currency": "USD",
            },
            "amountRefunded": {
                "amount": refunded_value,
                "currency": "USD",
            },
            "amountVoided": {
                "amount": voided_value,
                "currency": "USD",
            },
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = TransactionItem.objects.first()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]
    assert data["actions"] == available_actions
    assert data["status"] == status
    assert data["pspReference"] == psp_reference
    assert data["authorizedAmount"]["amount"] == authorized_value
    assert data["chargedAmount"]["amount"] == charged_value
    assert data["refundedAmount"]["amount"] == refunded_value
    assert data["voidedAmount"]["amount"] == voided_value

    assert transaction.authorized_value == authorized_value
    assert transaction.charged_value == charged_value
    assert transaction.voided_value == voided_value
    assert transaction.refunded_value == refunded_value


def test_transaction_create_create_event_for_order_by_staff(
    order_with_lines, permission_manage_payments, staff_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    transaction_status = "PENDING"
    transaction_reference = "transaction reference"
    transaction_name = "Processing transaction"

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
        },
        "transaction_event": {
            "status": transaction_status,
            "pspReference": transaction_reference,
            "name": transaction_name,
        },
    }

    # when
    staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    event = order_with_lines.events.first()

    assert event.type == OrderEvents.TRANSACTION_EVENT
    assert event.parameters == {
        "message": transaction_name,
        "reference": transaction_reference,
        "status": transaction_status.lower(),
    }


def test_transaction_create_missing_permission_by_staff(
    order_with_lines, staff_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
    }

    # when
    response = staff_api_client.post_graphql(MUTATION_TRANSACTION_CREATE, variables)

    # then
    assert_no_permission(response)


@pytest.mark.parametrize(
    "amount_field_name, amount_db_field",
    [
        ("amountAuthorized", "authorized_value"),
        ("amountCharged", "charged_value"),
        ("amountVoided", "voided_value"),
        ("amountRefunded", "refunded_value"),
    ],
)
def test_transaction_create_incorrect_currency_by_staff(
    amount_field_name,
    amount_db_field,
    order_with_lines,
    permission_manage_payments,
    staff_api_client,
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    expected_value = Decimal("10")

    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": [],
            amount_field_name: {
                "amount": expected_value,
                "currency": "PLN",
            },
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]
    assert data["errors"][0]["field"] == amount_field_name
    assert (
        data["errors"][0]["code"] == TransactionCreateErrorCode.INCORRECT_CURRENCY.name
    )


def test_transaction_create_empty_metadata_key_by_staff(
    order_with_lines, permission_manage_payments, staff_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}
    external_url = f"http://{TEST_SERVER_DOMAIN}.com/external-url"
    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
            "externalUrl": external_url,
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    content = get_graphql_content(response, ignore_errors=True)
    assert not content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.METADATA_KEY_REQUIRED.name


def test_transaction_create_empty_private_metadata_key_by_staff(
    order_with_lines, permission_manage_payments, staff_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "", "value": "321"}
    external_url = f"http://{TEST_SERVER_DOMAIN}.com/external-url"
    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
            "externalUrl": external_url,
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    content = get_graphql_content(response, ignore_errors=True)
    assert not content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.METADATA_KEY_REQUIRED.name


def test_transaction_create_external_url_incorrect_url_format_by_staff(
    order_with_lines, permission_manage_payments, staff_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test", "value": "321"}
    external_url = "incorrect"
    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
            "externalUrl": external_url,
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    content = get_graphql_content(response, ignore_errors=True)
    assert not content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.INVALID.name


def test_creates_transaction_event_incorrect_external_url_by_staff(
    order_with_lines, permission_manage_payments, staff_api_client
):
    # given
    status = "Failed authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = []
    authorized_value = Decimal("0")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    event_psp_reference = "PSP-ref"
    event_name = "Failed authorization"
    external_url = "incorrect"
    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
        "transaction_event": {
            "status": TransactionEventStatusEnum.FAILURE.name,
            "pspReference": event_psp_reference,
            "name": event_name,
            "externalUrl": external_url,
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    content = get_graphql_content(response, ignore_errors=True)
    assert not content["data"]["transactionCreate"]["transaction"]
    errors = content["data"]["transactionCreate"]["errors"]
    assert len(errors) == 1
    error = errors[0]
    assert error["code"] == TransactionCreateErrorCode.INVALID.name


def test_creates_transaction_event_for_order_by_staff(
    order_with_lines, permission_manage_payments, staff_api_client
):
    # given
    status = "Failed authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = []
    authorized_value = Decimal("0")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    event_status = TransactionEventStatus.FAILURE
    event_psp_reference = "PSP-ref"
    event_name = "Failed authorization"
    variables = {
        "id": graphene.Node.to_global_id("Order", order_with_lines.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
        "transaction_event": {
            "status": TransactionEventStatusEnum.FAILURE.name,
            "pspReference": event_psp_reference,
            "name": event_name,
            "amount": authorized_value,
            "type": TransactionEventActionTypeEnum.AUTHORIZE.name,
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = order_with_lines.payment_transactions.first()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]

    events_data = data["events"]
    assert len(events_data) == 1
    event_data = events_data[0]
    assert event_data["name"] == event_name
    assert event_data["status"] == TransactionEventStatusEnum.FAILURE.name
    assert event_data["pspReference"] == event_psp_reference
    assert event_data["amount"]["currency"] == transaction.currency
    assert event_data["amount"]["amount"] == authorized_value
    assert event_data["type"] == TransactionEventActionTypeEnum.AUTHORIZE.name

    assert transaction.events.count() == 1
    event = transaction.events.first()
    assert event.name == event_name
    assert event.status == event_status
    assert event.psp_reference == event_psp_reference
    assert event.amount_value == authorized_value
    assert event.currency == transaction.currency
    assert event.type == TransactionEventActionTypeEnum.AUTHORIZE.value


def test_creates_transaction_event_for_checkout_by_staff(
    checkout_with_items, permission_manage_payments, staff_api_client
):
    # given
    status = "Authorized for 10$"
    type = "Credit Card"
    psp_reference = "PSP reference - 123"
    available_actions = [
        TransactionActionEnum.CHARGE.name,
        TransactionActionEnum.VOID.name,
    ]
    authorized_value = Decimal("10")
    metadata = {"key": "test-1", "value": "123"}
    private_metadata = {"key": "test-2", "value": "321"}

    event_status = TransactionEventStatus.FAILURE
    event_psp_reference = "PSP-ref"
    event_name = "Failed authorization"

    variables = {
        "id": graphene.Node.to_global_id("Checkout", checkout_with_items.pk),
        "transaction": {
            "status": status,
            "type": type,
            "pspReference": psp_reference,
            "availableActions": available_actions,
            "amountAuthorized": {
                "amount": authorized_value,
                "currency": "USD",
            },
            "metadata": [metadata],
            "privateMetadata": [private_metadata],
        },
        "transaction_event": {
            "status": TransactionEventStatusEnum.FAILURE.name,
            "pspReference": event_psp_reference,
            "name": event_name,
            "amount": authorized_value,
            "type": TransactionEventActionTypeEnum.AUTHORIZE.name,
        },
    }

    # when
    response = staff_api_client.post_graphql(
        MUTATION_TRANSACTION_CREATE, variables, permissions=[permission_manage_payments]
    )

    # then
    transaction = checkout_with_items.payment_transactions.first()
    content = get_graphql_content(response)
    data = content["data"]["transactionCreate"]["transaction"]

    events_data = data["events"]
    assert len(events_data) == 1
    event_data = events_data[0]
    assert event_data["name"] == event_name
    assert event_data["status"] == TransactionEventStatusEnum.FAILURE.name
    assert event_data["pspReference"] == event_psp_reference
    assert event_data["amount"]["currency"] == transaction.currency
    assert event_data["amount"]["amount"] == authorized_value
    assert event_data["type"] == TransactionEventActionTypeEnum.AUTHORIZE.name

    assert transaction.events.count() == 1
    event = transaction.events.first()
    assert event.name == event_name
    assert event.status == event_status
    assert event.psp_reference == event_psp_reference
    assert event.amount_value == authorized_value
    assert event.currency == transaction.currency
    assert event.type == TransactionEventActionTypeEnum.AUTHORIZE.value
