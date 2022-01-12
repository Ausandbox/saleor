import graphene

from ....graphql.core.types import Error
from . import enums

OAuth2ErrorCode = graphene.Enum.from_enum(enums.OAuth2ErrorCode)


class OAuth2Error(Error):
    code = OAuth2ErrorCode(description="The error code", required=True)


class ProviderEnum(graphene.Enum):
    GOOGLE = "google"
    FACEBOOK = "facebook"


class OAuth2Input(graphene.InputObjectType):
    provider = ProviderEnum(required=True, description="Provider name")
    code = graphene.String(required=True)
    state = graphene.String(required=True)
    redirect_url = graphene.String(required=True)
    channel = graphene.String(required=False)


class OAuth2TokenInput(graphene.InputObjectType):
    provider = ProviderEnum(required=True, description="Provider name")
    token = graphene.String(required=True, description="Provider access token.")


# @extend(fields="id")
# class User(graphene.ObjectType):
#     id = external(graphene.String(required=True))
