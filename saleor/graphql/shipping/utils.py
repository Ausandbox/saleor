from typing import TYPE_CHECKING, List, Optional

from django.core.exceptions import ValidationError
from measurement.measures import Weight

from ...account.models import Address
from ...plugins.base_plugin import ExcludedShippingMethod
from ...plugins.base_plugin import ShippingMethod as ShippingMethodDataclass
from ...shipping import models as shipping_models
from ...shipping.interface import ShippingMethodData
from ...shipping.models import ShippingMethod
from ..channel import ChannelContext
from ..core.utils import from_global_id_or_error

if TYPE_CHECKING:
    from ...plugins.manager import PluginsManager
    from ...shipping.models import ShippingMethodChannelListing


def get_shipping_model_by_object_id(
    object_id: Optional[str], raise_error: bool = True
) -> Optional[ShippingMethod]:
    if object_id:
        _, object_pk = from_global_id_or_error(object_id)
        shipping_method = ShippingMethod.objects.filter(pk=object_pk).first()
        if not shipping_method and raise_error:
            raise ValidationError(
                {
                    "id": ValidationError(
                        "Couldn't resolve to a node: %s" % object_id, code="not_found"
                    )
                }
            )
        return shipping_method
    return None


def get_instances_by_object_ids(object_ids: List[str]) -> List[ShippingMethod]:
    model_ids = []
    for object_id in object_ids:
        _, object_pk = from_global_id_or_error(object_id)
        model_ids.append(object_pk)
    return ShippingMethod.objects.filter(pk__in=model_ids)


def convert_shipping_method_model_to_dataclass(
    shipping_method: shipping_models.ShippingMethod,
):
    shipping_method_dataclass = ShippingMethodDataclass(
        id=str(shipping_method.id),
        price=shipping_method.price,  # type: ignore
        name=shipping_method.name,
        maximum_delivery_days=shipping_method.maximum_delivery_days,
        minimum_delivery_days=shipping_method.minimum_delivery_days,
        maximum_order_weight=None,
        minimum_order_weight=None,
    )
    if max_weight := shipping_method.maximum_order_weight:
        shipping_method_dataclass.maximum_order_weight = Weight(
            unit=max_weight.unit,
            value=max_weight.value,
        )

    if min_weight := shipping_method.maximum_order_weight:
        shipping_method_dataclass.minimum_order_weight = Weight(
            unit=min_weight.unit,
            value=min_weight.value,
        )
    return shipping_method_dataclass


def annotate_shipping_methods_with_price(
    shipping_methods: List[ShippingMethodData],
    channel_listings: List["ShippingMethodChannelListing"],
    address: Optional["Address"],
    channel_slug: str,
    manager: "PluginsManager",
    display_gross: bool,
):
    if not address:
        return
    channel_listing_map = {
        str(channel_listing.shipping_method_id): channel_listing
        for channel_listing in channel_listings
    }
    for method in shipping_methods:
        shipping_channel_listing = channel_listing_map[method.id]
        taxed_price = manager.apply_taxes_to_shipping(
            shipping_channel_listing.price, address, channel_slug
        )
        if display_gross:
            method.price = taxed_price.gross
        else:
            method.price = taxed_price.net


def annotate_active_shipping_methods(
    shipping_methods: List[ShippingMethodData],
    excluded_methods: List[ExcludedShippingMethod],
):
    for instance in shipping_methods:
        instance.active = True
        instance.message = ""
        for method in excluded_methods:
            if str(instance.id) == str(method.id):
                instance.active = False
                instance.message = method.reason


def wrap_with_channel_context(
    shipping_methods: List[shipping_models.ShippingMethod],
    channel_slug: str,
) -> List[ChannelContext]:
    instances = [
        ChannelContext(
            node=method,
            channel_slug=channel_slug,
        )
        for method in shipping_methods
    ]
    return instances
