from unittest.mock import patch
from urllib.parse import urlencode

from django.contrib.auth.tokens import default_token_generator
from django.test import override_settings

from ......account import events as account_events
from ......account.models import User
from ......account.notifications import get_default_user_payload
from ......account.search import generate_user_fields_search_document_value
from ......core.notify_events import NotifyEventType
from ......core.tests.utils import get_site_context_payload
from ......core.utils.url import prepare_url
from .....tests.utils import get_graphql_content

ACCOUNT_REGISTER_MUTATION = """
    mutation RegisterAccount(
        $input: AccountRegisterInput!
    ) {
        accountRegister(
            input: $input
        ) {
            errors {
                field
                message
                code
            }
            user {
                id
                email
            }
        }
    }
"""


@override_settings(
    ENABLE_ACCOUNT_CONFIRMATION_BY_EMAIL=True, ALLOWED_CLIENT_HOSTS=["localhost"]
)
@patch("saleor.account.notifications.default_token_generator.make_token")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_customer_register(
    mocked_notify,
    mocked_generator,
    api_client,
    channel_PLN,
    order,
    site_settings,
):
    # given
    mocked_generator.return_value = "token"
    email = "customer@example.com"

    redirect_url = "http://localhost:3000"
    variables = {
        "input": {
            "email": email,
            "password": "Password",
            "redirectUrl": redirect_url,
            "firstName": "saleor",
            "lastName": "rocks",
            "languageCode": "PL",
            "metadata": [{"key": "meta", "value": "data"}],
            "channel": channel_PLN.slug,
        }
    }
    query = ACCOUNT_REGISTER_MUTATION
    mutation_name = "accountRegister"

    # when
    response = api_client.post_graphql(query, variables)

    content = get_graphql_content(response)
    data = content["data"][mutation_name]

    # then
    new_user = User.objects.get(email=email)
    params = urlencode({"email": email, "token": "token"})
    confirm_url = prepare_url(params, redirect_url)

    expected_payload = {
        "user": get_default_user_payload(new_user),
        "token": "token",
        "confirm_url": confirm_url,
        "recipient_email": new_user.email,
        "channel_slug": channel_PLN.slug,
        **get_site_context_payload(site_settings.site),
    }
    assert new_user.metadata == {"meta": "data"}
    assert new_user.language_code == "pl"
    assert new_user.first_name == variables["input"]["firstName"]
    assert new_user.last_name == variables["input"]["lastName"]
    assert new_user.search_document == generate_user_fields_search_document_value(
        new_user
    )
    assert not data["errors"]
    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_CONFIRMATION,
        payload=expected_payload,
        channel_slug=channel_PLN.slug,
    )


@override_settings(
    ENABLE_ACCOUNT_CONFIRMATION_BY_EMAIL=True, ALLOWED_CLIENT_HOSTS=["localhost"]
)
@patch("saleor.account.notifications.default_token_generator.make_token")
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_customer_register_twice(
    mocked_notify,
    mocked_generator,
    api_client,
    channel_PLN,
    order,
    site_settings,
):
    # given
    mocked_generator.return_value = "token"
    email = "customer@example.com"

    redirect_url = "http://localhost:3000"
    variables = {
        "input": {
            "email": email,
            "password": "Password",
            "redirectUrl": redirect_url,
            "firstName": "saleor",
            "lastName": "rocks",
            "languageCode": "PL",
            "metadata": [{"key": "meta", "value": "data"}],
            "channel": channel_PLN.slug,
        }
    }
    query = ACCOUNT_REGISTER_MUTATION
    mutation_name = "accountRegister"

    # when
    response = api_client.post_graphql(query, variables)

    content = get_graphql_content(response)
    data = content["data"][mutation_name]

    # then
    new_user = User.objects.get(email=email)
    params = urlencode({"email": email, "token": "token"})
    confirm_url = prepare_url(params, redirect_url)

    expected_payload = {
        "user": get_default_user_payload(new_user),
        "token": "token",
        "confirm_url": confirm_url,
        "recipient_email": new_user.email,
        "channel_slug": channel_PLN.slug,
        **get_site_context_payload(site_settings.site),
    }
    assert new_user.metadata == {"meta": "data"}
    assert new_user.language_code == "pl"
    assert new_user.first_name == variables["input"]["firstName"]
    assert new_user.last_name == variables["input"]["lastName"]
    assert new_user.search_document == generate_user_fields_search_document_value(
        new_user
    )
    assert not data["errors"]
    mocked_notify.assert_called_once_with(
        NotifyEventType.ACCOUNT_CONFIRMATION,
        payload=expected_payload,
        channel_slug=channel_PLN.slug,
    )

    response = api_client.post_graphql(query, variables)
    content = get_graphql_content(response)
    data = content["data"][mutation_name]
    assert not data["errors"]

    customer_creation_event = account_events.CustomerEvent.objects.get()
    assert customer_creation_event.type == account_events.CustomerEvents.ACCOUNT_CREATED
    assert customer_creation_event.user == new_user


@override_settings(
    ENABLE_ACCOUNT_CONFIRMATION_BY_EMAIL=True, ALLOWED_CLIENT_HOSTS=["localhost"]
)
@patch("saleor.plugins.manager.PluginsManager.notify")
def test_customer_register_generates_valid_token(
    mocked_notify,
    api_client,
    channel_PLN,
    order,
    site_settings,
):
    # given
    email = "customer@example.com"
    redirect_url = "http://localhost:3000"
    variables = {
        "input": {
            "email": email,
            "password": "Password",
            "redirectUrl": redirect_url,
            "firstName": "saleor",
            "lastName": "rocks",
            "languageCode": "PL",
            "metadata": [{"key": "meta", "value": "data"}],
            "channel": channel_PLN.slug,
        }
    }

    # when
    response = api_client.post_graphql(ACCOUNT_REGISTER_MUTATION, variables)
    new_user = User.objects.get(email=email)
    content = get_graphql_content(response)
    data = content["data"]["accountRegister"]

    # then
    token = mocked_notify.call_args.kwargs["payload"]["token"]
    assert not data["errors"]
    assert default_token_generator.check_token(new_user, token)


@patch("saleor.plugins.manager.PluginsManager.notify")
def test_customer_register_disabled_email_confirmation(
    mocked_notify, api_client, site_settings
):
    # given
    site_settings.enable_account_confirmation_by_email = False
    site_settings.save(update_fields=["enable_account_confirmation_by_email"])

    email = "customer@example.com"
    variables = {"input": {"email": email, "password": "Password"}}

    #   when
    response = api_client.post_graphql(ACCOUNT_REGISTER_MUTATION, variables)
    errors = response.json()["data"]["accountRegister"]["errors"]

    # then
    assert errors == []
    created_user = User.objects.get()
    expected_payload = get_default_user_payload(created_user)
    expected_payload["token"] = "token"
    expected_payload["redirect_url"] = "http://localhost:3000"
    mocked_notify.assert_not_called()


@patch("saleor.plugins.manager.PluginsManager.notify")
def test_customer_register_no_redirect_url(mocked_notify, api_client, site_settings):
    # given
    site_settings.enable_account_confirmation_by_email = True
    site_settings.save(update_fields=["enable_account_confirmation_by_email"])

    variables = {"input": {"email": "customer@example.com", "password": "Password"}}

    #   when
    response = api_client.post_graphql(ACCOUNT_REGISTER_MUTATION, variables)
    errors = response.json()["data"]["accountRegister"]["errors"]

    # then
    assert "redirectUrl" in map(lambda error: error["field"], errors)
    mocked_notify.assert_not_called()


@override_settings(ENABLE_ACCOUNT_CONFIRMATION_BY_EMAIL=False)
def test_customer_register_upper_case_email(api_client, site_settings):
    # given
    site_settings.enable_account_confirmation_by_email = False
    site_settings.save(update_fields=["enable_account_confirmation_by_email"])

    email = "CUSTOMER@example.com"
    variables = {"input": {"email": email, "password": "Password"}}

    # when
    response = api_client.post_graphql(ACCOUNT_REGISTER_MUTATION, variables)
    content = get_graphql_content(response)

    # then
    data = content["data"]["accountRegister"]
    assert not data["errors"]
    assert data["user"]["email"].lower()


@patch("saleor.plugins.manager.PluginsManager.notify")
def test_customer_register_no_channel_email_confirmation_unset(
    mocked_notify, api_client, channel_PLN, site_settings
):
    # given
    site_settings.enable_account_confirmation_by_email = False
    site_settings.save(update_fields=["enable_account_confirmation_by_email"])

    email = "customer@example.com"
    redirect_url = "http://localhost:3000"
    variables = {
        "input": {
            "email": email,
            "password": "Password",
            "redirectUrl": redirect_url,
            "firstName": "saleor",
            "lastName": "rocks",
            "languageCode": "PL",
            "metadata": [{"key": "meta", "value": "data"}],
        }
    }

    # when
    response = api_client.post_graphql(ACCOUNT_REGISTER_MUTATION, variables)
    content = get_graphql_content(response)
    data = content["data"]["accountRegister"]

    # then
    data = content["data"]["accountRegister"]
    assert not data["errors"]
    assert data["user"]["email"].lower()
    mocked_notify.assert_not_called()


def test_account_register_properly_filter_errors(
    api_client, channel_PLN, site_settings
):
    # given
    site_settings.enable_account_confirmation_by_email = False
    site_settings.save(update_fields=["enable_account_confirmation_by_email"])

    email = "customer"
    variables = {
        "input": {
            "email": email,
            "password": "Password",
            "firstName": "saleor",
            "lastName": "rocks",
        }
    }

    # when
    response = api_client.post_graphql(ACCOUNT_REGISTER_MUTATION, variables)
    content = get_graphql_content(response)

    # then
    errors = content["data"]["accountRegister"]["errors"]
    assert errors
    assert errors[0]["code"] == "INVALID"
    assert errors[0]["field"] == "email"


def test_account_register_returns_empty_id(
    api_client, channel_PLN, site_settings, customer_user
):
    # given
    site_settings.enable_account_confirmation_by_email = False
    site_settings.save(update_fields=["enable_account_confirmation_by_email"])

    variables = {
        "input": {
            "email": customer_user.email,
            "password": "Password",
        }
    }

    # when
    response = api_client.post_graphql(ACCOUNT_REGISTER_MUTATION, variables)
    content = get_graphql_content(response)

    # then
    data = content["data"]["accountRegister"]
    assert not data["errors"]
    assert data["user"]["id"] == ""
    assert data["user"]["email"] == customer_user.email
