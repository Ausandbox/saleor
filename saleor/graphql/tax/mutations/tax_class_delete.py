import graphene
from django.core.exceptions import ValidationError

from ....core.permissions import TaxPermissions
from ....tax import error_codes, models
from ...core.descriptions import ADDED_IN_35, PREVIEW_FEATURE
from ...core.mutations import ModelDeleteMutation
from ...core.types import Error
from ..types import TaxClass

TaxClassDeleteErrorCode = graphene.Enum.from_enum(error_codes.TaxClassDeleteErrorCode)


class TaxClassDeleteError(Error):
    code = TaxClassDeleteErrorCode(description="The error code.", required=True)


class TaxClassDelete(ModelDeleteMutation):
    class Arguments:
        id = graphene.ID(required=True, description="ID of a tax class to delete.")

    class Meta:
        description = (
            (
                "Delete a tax class. After deleting the tax class any products, "
                "product types or shipping methods using it are updated to use the "
                "default tax class."
            )
            + ADDED_IN_35
            + PREVIEW_FEATURE
        )
        error_type_class = TaxClassDeleteError
        model = models.TaxClass
        object_type = TaxClass
        permissions = (TaxPermissions.MANAGE_TAXES,)

    @classmethod
    def clean_instance(cls, info, instance):
        if instance.is_default:
            code = error_codes.TaxClassDeleteErrorCode.CANNOT_DELETE_DEFAULT_CLASS.value
            raise ValidationError(
                {
                    "id": ValidationError(
                        "Cannot delete a default tax class.",
                        code=code,
                    )
                }
            )
