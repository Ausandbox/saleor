import graphene

from ....permission.enums import CheckoutPermissions
from ...core.mutations import BaseMutation
from ...core.types.common import CheckoutError

from ...order.mutations.order_discount_common import DiscountCommonInput
from ..types import Checkout


class CheckoutDiscountUpdate(BaseMutation):
    checkout = graphene.Field(
        Checkout, description="Checkout which has been discounted."
    )

    class Arguments:
        discount_id = graphene.ID(
            description="ID of a discount to update.", required=True
        )
        input = DiscountCommonInput(
            required=True,
            description="Fields required to update a discount for the checkout.",
        )

    class Meta:
        description = "Update discount to the checkout."
        permissions = (CheckoutPermissions.MANAGE_CHECKOUTS,)
        error_type_class = CheckoutError
