# auth/swagger_oauth.py
# OAuth2 configuration for Swagger UI integration with Identity Server
# NOTE: fastapi-service only supports client_credentials, NOT authorization_code
# Swagger OAuth redirect will NOT work - use manual token instead

import os
from typing import Optional

# DISABLE Swagger OAuth since fastapi-service doesn't support authorization_code
ENABLE_SWAGGER_OAUTH = False

# Identity Server OAuth2 Configuration (matches actual client config)
OAUTH2_CONFIG = {
    "authorization_url": f"{os.getenv('IDENTITY_SERVER_ISSUER')}/connect/authorize",
    "token_url": f"{os.getenv('IDENTITY_SERVER_ISSUER')}/connect/token",
    "scopes": {
        # Only scopes available in fastapi-service client:
        "api1": "Full API access",
        "api1.read": "Read access to API",
        # NOTE: openid, profile, api1.write are NOT available
    },
}

# Swagger UI OAuth2 initialization parameters
SWAGGER_UI_INIT_OAUTH = {
    "clientId": os.getenv("IDENTITY_SERVER_CLIENT_ID", "fastapi-service"),
    "usePkceWithAuthorizationCodeGrant": True,
    "scopes": "api1 api1.read",  # Only available scopes
}


def get_oauth2_scheme_config() -> Optional[dict]:
    """
    Returns OAuth2 security scheme for OpenAPI spec.

    NOTE: This is DISABLED because fastapi-service only supports
    client_credentials grant, not authorization_code.

    To enable Swagger OAuth redirect, you need to update fastapi-service in
    Identity Server with:
    - AllowedGrantTypes: ["client_credentials", "authorization_code"]
    - RedirectUris: ["http://127.0.0.1:8000/docs/oauth2-redirect"]
    - AllowedScopes: ["openid", "profile", "api1", "api1.read"]
    """
    if not ENABLE_SWAGGER_OAUTH:
        return None

    return {
        "type": "oauth2",
        "flows": {
            "authorizationCode": {
                "authorizationUrl": OAUTH2_CONFIG["authorization_url"],
                "tokenUrl": OAUTH2_CONFIG["token_url"],
                "scopes": OAUTH2_CONFIG["scopes"],
            }
        },
    }


def get_swagger_ui_parameters() -> dict:
    """
    Returns parameters for FastAPI swagger_ui_parameters.
    Currently disabled - manual token entry required.
    """
    if not ENABLE_SWAGGER_OAUTH:
        return {}

    return {"initOAuth": SWAGGER_UI_INIT_OAUTH}
