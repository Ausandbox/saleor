import logging

from django.core.exceptions import ValidationError
from django.core.handlers.wsgi import WSGIRequest
from django.http import HttpResponse, HttpResponseNotFound

from ....graphql.core.enums import PluginErrorCode
from ....plugins.base_plugin import BasePlugin, ConfigurationTypeField

from ...interface import (
    CustomerSource,
    GatewayConfig,
    GatewayResponse,
    PaymentData,
    PaymentMethodInfo,
)

from .consts import (
    PLUGIN_ID,
    PLUGIN_NAME,
)

logger = logging.getLogger(__name__)

class PayfastGatewayPlugin(BasePlugin):
    PLUGIN_NAME = PLUGIN_NAME
    PLUGIN_ID = PLUGIN_ID

    DEFAULT_CONFIGURATION = [
        {"name": "api_endpoint", "value": ""},
        {"name": "merchant_id", "value": None},
        {"name": "public_api_key", "value": None},
        {"name": "automatic_payment_capture", "value": True},
        {"name": "supported_currencies", "value": ""},
        {"name": "merchant_passphrase", "value": None},
        {"name": "return_url", "value": None},
        {"name": "cancel_url", "value": None},
        {"name": "notify_url", "value": None},
    ]

    CONFIG_STRUCTURE = {
        "api_endpoint": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Provide Payfast public API url.",
            "label": "Payfast API url",
        },
        "merchant_id": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Provide your Payfast merchant ID.",
            "label": "Payfast merchant ID",
        },
        "public_api_key": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Provide Payfast public API key.",
            "label": "Public API key",
        },
        "automatic_payment_capture": {
            "type": ConfigurationTypeField.BOOLEAN,
            "help_text": "Determines if Saleor should automatically capture payments.",
            "label": "Automatic payment capture",
        },
        "supported_currencies": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Determines currencies supported by gateway."
            " Please enter currency codes separated by a comma.",
            "label": "Supported currencies",
        },
        "merchant_passphrase": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Add your merchant passphrase.",
            "label": "Merchant passphrase",
        },
        "return_url": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Provide return url.",
            "label": "Return here after payment completion",
        },
        "cancel_url": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Provide cancel url.",
            "label": "Transaction cancelled url",
        },
        "notify_url": {
            "type": ConfigurationTypeField.STRING,
            "help_text": "Provide Payfast notify url.",
            "label": "Callback url after payment processing",
        },
    }

    def __init__(self, *, configuration, **kwargs):

        super().__init__(configuration=configuration, **kwargs)
        configuration = {item["name"]: item["value"] for item in self.configuration}
        self.config = GatewayConfig(
            gateway_name=PLUGIN_NAME,
            auto_capture=configuration["automatic_payment_capture"],
            supported_currencies=configuration["supported_currencies"],
            connection_params={
                "api_endpoint": configuration["api_endpoint"],
                "merchant_id": configuration["merchant_id"],
                "public_api_key": configuration["public_api_key"],
                "merchant_passphrase": configuration["merchant_passphrase"],
                "return_url": configuration["return_url"],
                "cancel_url": configuration["cancel_url"],
                "notify_url": configuration["notify_url"],
            },
            store_customer=True,
        )

    @classmethod
    def validate_plugin_configuration(
        cls, plugin_configuration: "PluginConfiguration", **kwargs
    ):
        configuration = plugin_configuration.configuration
        configuration = {item["name"]: item["value"] for item in configuration}
        required_fields = ["api_endpoint", "merchant_id", "public_api_key",
                           "merchant_passphrase", "notify_url"]
        all_required_fields_provided = all(
            [configuration.get(field) for field in required_fields]
        )
        if plugin_configuration.active:
            if not all_required_fields_provided:
                raise ValidationError(
                    {
                        field: ValidationError(
                            "The parameter is required.",
                            code=PluginErrorCode.REQUIRED.value,
                        )
                        for field in required_fields
                    }
                )

    def process_payment(self, payment_information: "PaymentData",
                        previous_value) -> "GatewayResponse":
        if not self.active:
            return previous_value



    def webhook(self, request: WSGIRequest, path: str, previous_value) -> HttpResponse:
        logger.warning(
            "Received request to incorrect stripe path", extra={"path": path}
        )
        return HttpResponse(status=200)


