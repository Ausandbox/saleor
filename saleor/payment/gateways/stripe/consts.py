PLUGIN_ID = "saleor.payments.stripe"
PLUGIN_NAME = "Stripe"
WEBHOOK_PATH = "webhooks/"
WEBHOOK_EVENTS = [
    "payment_intent.payment_failed",
    "payment_intent.succeeded",
    "payment_intent.processing",
]
METADATA_IDENTIFIER = "saleor-domain"

ACTION_REQUIRED_STATUSES = [
    "requires_payment_method",
    "requires_confirmation",
    "requires_action",
]
FAILED_STATUSES = ["requires_payment_method" "canceled"]

SUCCESS_STATUS = "succeeded"

PROCESSING_STATUS = "processing"
