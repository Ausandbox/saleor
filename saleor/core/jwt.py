from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional

import graphene
import jwt
from django.conf import settings

from ..account.models import User
from ..app.models import App, AppExtension
from ..permission.models import Permission
from .jwt_manager import get_jwt_manager
from .permissions import (
    get_permission_names,
    get_permissions_from_codenames,
    get_permissions_from_names,
)

JWT_ACCESS_TYPE = "access"
JWT_REFRESH_TYPE = "refresh"
JWT_THIRDPARTY_ACCESS_TYPE = "thirdparty"
JWT_REFRESH_TOKEN_COOKIE_NAME = "refreshToken"

PERMISSIONS_FIELD = "permissions"
USER_PERMISSION_FIELD = "user_permissions"
JWT_SALEOR_OWNER_NAME = "saleor"
JWT_OWNER_FIELD = "owner"


def jwt_base_payload(
    exp_delta: Optional[timedelta], token_owner: str
) -> Dict[str, Any]:
    utc_now = datetime.utcnow()

    payload = {
        "iat": utc_now,
        JWT_OWNER_FIELD: token_owner,
        "iss": get_jwt_manager().get_issuer(),
    }
    if exp_delta:
        payload["exp"] = utc_now + exp_delta
    return payload


def jwt_user_payload(
    user: User,
    token_type: str,
    exp_delta: Optional[timedelta],
    additional_payload: Optional[Dict[str, Any]] = None,
    token_owner: str = JWT_SALEOR_OWNER_NAME,
) -> Dict[str, Any]:

    payload = jwt_base_payload(exp_delta, token_owner)
    payload.update(
        {
            "token": user.jwt_token_key,
            "email": user.email,
            "type": token_type,
            "user_id": graphene.Node.to_global_id("User", user.id),
            "is_staff": user.is_staff,
        }
    )
    if additional_payload:
        payload.update(additional_payload)
    return payload


def jwt_encode(payload: Dict[str, Any]) -> str:
    jwt_manager = get_jwt_manager()
    return jwt_manager.encode(payload)


def jwt_decode_with_exception_handler(
    token: str, verify_expiration=settings.JWT_EXPIRE
) -> Optional[Dict[str, Any]]:
    try:
        return jwt_decode(token, verify_expiration=verify_expiration)
    except jwt.PyJWTError:
        return None


def jwt_decode(
    token: str, verify_expiration=settings.JWT_EXPIRE, verify_aud: bool = False
) -> Dict[str, Any]:
    jwt_manager = get_jwt_manager()
    return jwt_manager.decode(token, verify_expiration, verify_aud=verify_aud)


def create_token(payload: Dict[str, Any], exp_delta: timedelta) -> str:
    payload.update(jwt_base_payload(exp_delta, token_owner=JWT_SALEOR_OWNER_NAME))
    return jwt_encode(payload)


def create_access_token(
    user: User, additional_payload: Optional[Dict[str, Any]] = None
) -> str:
    payload = jwt_user_payload(
        user, JWT_ACCESS_TYPE, settings.JWT_TTL_ACCESS, additional_payload
    )
    return jwt_encode(payload)


def create_refresh_token(
    user: User, additional_payload: Optional[Dict[str, Any]] = None
) -> str:
    payload = jwt_user_payload(
        user,
        JWT_REFRESH_TYPE,
        settings.JWT_TTL_REFRESH,
        additional_payload,
    )
    return jwt_encode(payload)


def get_user_from_payload(payload: Dict[str, Any]) -> Optional[User]:
    user = User.objects.filter(email=payload["email"], is_active=True).first()
    user_jwt_token = payload.get("token")
    if not user_jwt_token or not user:
        raise jwt.InvalidTokenError(
            "Invalid token. Create new one by using tokenCreate mutation."
        )
    if user.jwt_token_key != user_jwt_token:
        raise jwt.InvalidTokenError(
            "Invalid token. Create new one by using tokenCreate mutation."
        )
    return user


def is_saleor_token(token: str) -> bool:
    """Confirm that token was generated by Saleor not by plugin."""
    try:
        payload = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return False
    owner = payload.get(JWT_OWNER_FIELD)
    if not owner or owner != JWT_SALEOR_OWNER_NAME:
        return False
    return True


def get_user_from_access_token(token: str) -> Optional[User]:
    if not is_saleor_token(token):
        return None
    payload = jwt_decode(token)
    return get_user_from_access_payload(payload)


def get_user_from_access_payload(payload: dict) -> Optional[User]:
    jwt_type = payload.get("type")
    if jwt_type not in [JWT_ACCESS_TYPE, JWT_THIRDPARTY_ACCESS_TYPE]:
        raise jwt.InvalidTokenError(
            "Invalid token. Create new one by using tokenCreate mutation."
        )
    permissions = payload.get(PERMISSIONS_FIELD, None)
    user = get_user_from_payload(payload)
    if user:
        if permissions is not None:
            token_permissions = get_permissions_from_names(permissions)
            token_codenames = [perm.codename for perm in token_permissions]
            user.effective_permissions = get_permissions_from_codenames(token_codenames)
            user.is_staff = True if user.effective_permissions else False

        if payload.get("is_staff"):
            user.is_staff = True
    return user


def _create_access_token_for_third_party_actions(
    permissions: Iterable["Permission"],
    user: "User",
    type: str,
    object_id: int,
    object_payload_key: str,
    audience: Optional[str],
):
    app_permission_enums = get_permission_names(permissions)

    permissions = user.effective_permissions
    user_permission_enums = get_permission_names(permissions)
    additional_payload = {
        object_payload_key: graphene.Node.to_global_id(type, object_id),
        PERMISSIONS_FIELD: list(app_permission_enums & user_permission_enums),
        USER_PERMISSION_FIELD: list(user_permission_enums),
    }
    if audience:
        additional_payload["aud"] = audience

    payload = jwt_user_payload(
        user,
        JWT_THIRDPARTY_ACCESS_TYPE,
        exp_delta=settings.JWT_TTL_APP_ACCESS,
        additional_payload=additional_payload,
    )
    return jwt_encode(payload)


def create_access_token_for_app(app: "App", user: "User"):
    """Create access token for app.

    App can use user's JWT token to proceed given operation in Saleor.
    The token which can be used by App has additional field defining the permissions
    assigned to it. The permissions set is the intersection of user permissions and
    app permissions.
    """
    app_permissions = app.permissions.all()
    return _create_access_token_for_third_party_actions(
        permissions=app_permissions,
        user=user,
        type="App",
        object_id=app.id,
        object_payload_key="app",
        audience=app.audience,
    )


def create_access_token_for_app_extension(
    app_extension: "AppExtension",
    permissions: Iterable["Permission"],
    user: "User",
    app: "App",
):
    return _create_access_token_for_third_party_actions(
        permissions=permissions,
        user=user,
        type="AppExtension",
        object_id=app_extension.id,
        object_payload_key="app_extension",
        audience=app.audience,
    )
