from unittest.mock import call, patch

import before_after
import pytest
from django.db import DatabaseError, OperationalError
from django.test import override_settings

from .....checkout.actions import call_checkout_event
from .....checkout.error_codes import CheckoutErrorCode
from .....checkout.models import Checkout
from .....core.models import EventDelivery
from .....webhook.event_types import WebhookEventAsyncType, WebhookEventSyncType
from ....core.utils import to_global_id_or_none
from ....tests.utils import get_graphql_content

MUTATION_CHECKOUT_UPDATE_LANGUAGE_CODE = """
mutation checkoutLanguageCodeUpdate($id: ID, $languageCode: LanguageCodeEnum!){
  checkoutLanguageCodeUpdate(id: $id, languageCode: $languageCode){
    checkout{
      id
      languageCode
    }
    errors{
      field
      message
      code
    }
  }
}
"""


def test_checkout_update_language_code(
    user_api_client,
    checkout_with_gift_card,
):
    language_code = "PL"
    checkout = checkout_with_gift_card
    previous_last_change = checkout.last_change
    variables = {"id": to_global_id_or_none(checkout), "languageCode": language_code}

    response = user_api_client.post_graphql(
        MUTATION_CHECKOUT_UPDATE_LANGUAGE_CODE, variables
    )

    content = get_graphql_content(response)
    data = content["data"]["checkoutLanguageCodeUpdate"]
    assert not data["errors"]

    assert data["checkout"]["languageCode"] == language_code
    checkout.refresh_from_db()
    assert checkout.language_code == language_code.lower()
    assert checkout.last_change != previous_last_change


def test_with_active_problems_flow(api_client, checkout_with_problems):
    # given
    channel = checkout_with_problems.channel
    channel.use_legacy_error_flow_for_checkout = False
    channel.save(update_fields=["use_legacy_error_flow_for_checkout"])

    variables = {
        "id": to_global_id_or_none(checkout_with_problems),
        "languageCode": "PL",
    }

    # when
    response = api_client.post_graphql(
        MUTATION_CHECKOUT_UPDATE_LANGUAGE_CODE,
        variables,
    )
    content = get_graphql_content(response)

    # then
    assert not content["data"]["checkoutLanguageCodeUpdate"]["errors"]


@patch(
    "saleor.graphql.checkout.mutations.checkout_language_code_update.call_checkout_event",
    wraps=call_checkout_event,
)
@patch("saleor.webhook.transport.synchronous.transport.send_webhook_request_sync")
@patch(
    "saleor.webhook.transport.asynchronous.transport.send_webhook_request_async.apply_async"
)
@override_settings(PLUGINS=["saleor.plugins.webhook.plugin.WebhookPlugin"])
def test_checkout_update_language_code_triggers_webhooks(
    mocked_send_webhook_request_async,
    mocked_send_webhook_request_sync,
    wrapped_call_checkout_event,
    setup_checkout_webhooks,
    settings,
    user_api_client,
    checkout_with_gift_card,
):
    # given
    mocked_send_webhook_request_sync.return_value = []
    (
        tax_webhook,
        shipping_webhook,
        shipping_filter_webhook,
        checkout_updated_webhook,
    ) = setup_checkout_webhooks(WebhookEventAsyncType.CHECKOUT_UPDATED)

    language_code = "PL"
    checkout = checkout_with_gift_card
    variables = {"id": to_global_id_or_none(checkout), "languageCode": language_code}

    # when
    response = user_api_client.post_graphql(
        MUTATION_CHECKOUT_UPDATE_LANGUAGE_CODE, variables
    )

    # then
    content = get_graphql_content(response)
    assert not content["data"]["checkoutLanguageCodeUpdate"]["errors"]

    # confirm that event delivery was generated for each webhook.
    checkout_update_delivery = EventDelivery.objects.get(
        webhook_id=checkout_updated_webhook.id
    )
    tax_delivery = EventDelivery.objects.get(webhook_id=tax_webhook.id)
    shipping_methods_delivery = EventDelivery.objects.get(
        webhook_id=shipping_webhook.id,
        event_type=WebhookEventSyncType.SHIPPING_LIST_METHODS_FOR_CHECKOUT,
    )
    filter_shipping_delivery = EventDelivery.objects.get(
        webhook_id=shipping_filter_webhook.id,
        event_type=WebhookEventSyncType.CHECKOUT_FILTER_SHIPPING_METHODS,
    )

    mocked_send_webhook_request_async.assert_called_once_with(
        kwargs={"event_delivery_id": checkout_update_delivery.id},
        queue=settings.CHECKOUT_WEBHOOK_EVENTS_CELERY_QUEUE_NAME,
        bind=True,
        retry_backoff=10,
        retry_kwargs={"max_retries": 5},
    )
    mocked_send_webhook_request_sync.assert_has_calls(
        [
            call(shipping_methods_delivery, timeout=settings.WEBHOOK_SYNC_TIMEOUT),
            call(filter_shipping_delivery, timeout=settings.WEBHOOK_SYNC_TIMEOUT),
            call(tax_delivery),
        ]
    )
    assert wrapped_call_checkout_event.called


def test_checkout_update_language_code_deleted_database_error(
    user_api_client,
    checkout_with_gift_card,
    customer_user2,
    permission_impersonate_user,
):
    # given
    language_code = "PL"
    variables = {
        "id": to_global_id_or_none(checkout_with_gift_card),
        "languageCode": language_code,
    }

    # when
    with before_after.before(
        (
            "saleor.graphql.checkout.mutations."
            "checkout_language_code_update.save_checkout_with_update_fields"
        ),
        lambda *args, **kwargs: Checkout.objects.all().delete(),
    ):
        response = user_api_client.post_graphql(
            MUTATION_CHECKOUT_UPDATE_LANGUAGE_CODE, variables
        )
    # then
    data = get_graphql_content(response)["data"]["checkoutLanguageCodeUpdate"]
    errors = data["errors"]

    assert len(errors) == 1
    assert errors[0]["field"] == "checkout"
    assert errors[0]["message"] == "Checkout does no longer exists."
    assert errors[0]["code"] == CheckoutErrorCode.DELETED.name


@pytest.mark.parametrize("error", [OperationalError, DatabaseError])
def test_checkout_update_language_code_raise_error_which_inherits_from_database_error(
    user_api_client,
    checkout_with_gift_card,
    customer_user2,
    permission_impersonate_user,
    error,
):
    # given
    language_code = "PL"
    variables = {
        "id": to_global_id_or_none(checkout_with_gift_card),
        "languageCode": language_code,
    }
    # when
    with patch.object(Checkout, "save", side_effect=error):
        response = user_api_client.post_graphql(
            MUTATION_CHECKOUT_UPDATE_LANGUAGE_CODE, variables
        )

    # then
    data = get_graphql_content(response, ignore_errors=True)
    errors = data["errors"]

    assert len(errors) == 1
    assert errors[0]["message"] == "Internal Server Error"
    assert errors[0]["extensions"]["exception"]["code"] == error.__name__
