from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from passlib.context import CryptContext
import os
import httpx
from typing import Optional
from core.config.logger import get_logger, configure_logging
import random

configure_logging()
logger = get_logger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
# Use HTTPBearer for simple token input in Swagger (no username/password dialog)
security = HTTPBearer(auto_error=False)
SECRET_KEY = os.environ.get("SECRET_KEY")
ALGORITHM = os.environ.get("ALGORITHM")
IDENTITY_SERVER_AUTHENTICATION = str(
    os.environ.get("IDENTITY_SERVER_AUTHENTICATION", "False")
)
AUTHENTICATION = str(os.environ.get("AUTHENTICATION", "False"))


# IdentityServer Configuration
IDENTITY_SERVER_CONFIG = {
    "issuer": os.environ.get("IDENTITY_SERVER_ISSUER"),
    "jwks_uri": os.environ.get("IDENTITY_SERVER_JWKS_URI"),
    "token_endpoint": os.environ.get("IDENTITY_SERVER_TOKEN_ENDPOINT"),
    "userinfo_endpoint": os.environ.get("IDENTITY_SERVER_USERINFO_ENDPOINT"),
    "introspection_endpoint": os.environ.get("IDENTITY_SERVER_INTROSPECTION_ENDPOINT"),
    "client_id": os.environ.get("IDENTITY_SERVER_CLIENT_ID"),
    "client_secret": os.environ.get("IDENTITY_SERVER_SECRET_KEY"),
    "allowed_scopes": ["api1", "api1.read"],
}


# IdentityServer Authentication Functions
async def GetToken() -> str:
    """
    Get an access token from IdentityServer using client credentials flow.
    This is used for service-to-service communication.
    """
    logger.info("GetToken: Starting IdentityServer token request")
    data = {
        "grant_type": "client_credentials",
        "client_id": IDENTITY_SERVER_CONFIG["client_id"],
        "client_secret": IDENTITY_SERVER_CONFIG["client_secret"],
        "scope": " ".join(IDENTITY_SERVER_CONFIG["allowed_scopes"]),
    }
    logger.info(f"Token endpoint: {IDENTITY_SERVER_CONFIG['token_endpoint']}")
    logger.info(f"Client ID: {IDENTITY_SERVER_CONFIG['client_id']}")
    logger.info(f"Requested scopes: {data['scope']}")
    async with httpx.AsyncClient() as client:
        try:
            logger.info("Sending token request to IdentityServer")
            response = await client.post(
                IDENTITY_SERVER_CONFIG["token_endpoint"], data=data, timeout=30.0
            )
            response.raise_for_status()
            token_data = response.json()
            logger.info("IdentityServer token received successfully")
            return token_data.get("access_token")
        except httpx.HTTPError as e:
            logger.error(f"Failed to get IdentityServer token: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Failed to authenticate with IdentityServer: {str(e)}",
            )


async def ValidateToken(token: str) -> dict:
    """
    Validate an access token with IdentityServer's introspection endpoint.
    Returns the token payload if valid.
    """
    logger.info("ValidateToken: Starting token validation")
    logger.info(f"Token (first 20 chars): {token[:20]}...")
    data = {
        "token": token,
        "client_id": IDENTITY_SERVER_CONFIG["client_id"],
        "client_secret": IDENTITY_SERVER_CONFIG["client_secret"],
    }
    logger.info(
        f"Introspection endpoint: {IDENTITY_SERVER_CONFIG['introspection_endpoint']}"
    )
    logger.info(f"Using client_id: {IDENTITY_SERVER_CONFIG['client_id']}")
    logger.info(
        f"Client secret length: {len(IDENTITY_SERVER_CONFIG.get('client_secret', ''))}"
    )
    async with httpx.AsyncClient() as client:
        try:
            logger.info("Sending token introspection request to IdentityServer")
            response = await client.post(
                IDENTITY_SERVER_CONFIG["introspection_endpoint"],
                data=data,
                timeout=30.0,
            )
            logger.info(f"Introspection response status code: {response.status_code}")
            logger.info(f"Response headers: {dict(response.headers)}")
            # Log response body even if there's an error
            try:
                response_body = response.text
                logger.info(f"Response body: {response_body[:500]}")
            except:
                pass
            response.raise_for_status()
            token_info = response.json()
            logger.info(
                f"Token introspection response received. Active: {token_info.get('active', False)}"
            )
            if not token_info.get("active", False):
                logger.error("Token is not active or invalid")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token is not active or invalid",
                )
            logger.info("Token validation successful")
            return token_info
        except httpx.HTTPError as e:
            logger.error(f"Failed to validate token with IdentityServer: {str(e)}")
            logger.error(f"HTTP Error details - Type: {type(e).__name__}")
            if hasattr(e, "response") and e.response is not None:
                logger.error(f"Response status: {e.response.status_code}")
                logger.error(f"Response body: {e.response.text[:500]}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Token validation failed: {str(e)}",
            )


async def GetCurrentUser(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> dict:
    """
    Dependency to get the current user from IdentityServer token.
    Uses HTTPBearer for simple token input in Swagger UI.
    """
    # Extract token from credentials
    token = credentials.credentials if credentials else None

    logger.info("GetCurrentUser: Starting authentication")
    logger.info(
        f"IDENTITY_SERVER_AUTHENTICATION flag: {IDENTITY_SERVER_AUTHENTICATION}"
    )
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        if AUTHENTICATION.lower() == "false" and not token:
            logger.info("Authentication is disabled - returning default user")
            return {
                "user_id": random.randint(100000, 999999),
                "scopes": [],
                "client_id": None,
                "token_info": {},
            }
        # If authentication is enabled but no token provided, raise exception
        if not token:
            logger.error("Authentication enabled but no token provided")
            raise credentials_exception
        # Check if IdentityServer authentication is enabled
        if IDENTITY_SERVER_AUTHENTICATION.lower() == "true":
            # Validate token with IdentityServer
            logger.info(
                "IdentityServer authentication enabled - Validating token with IdentityServer"
            )
            token_info = await ValidateToken(token)
            # Extract user information from token
            user_id = token_info.get("sub") or token_info.get("client_id")
            logger.info(f"Extracted user_id from IdentityServer token: {user_id}")
            if not user_id:
                logger.error("No user_id found in token info")
                raise credentials_exception
            logger.debug(
                f"Authenticated user via IdentityServer: {user_id}, type: {type(user_id)}"
            )
            scopes = token_info.get("scope", "").split()
            logger.debug(f"User scopes: {scopes}")
            return {
                "user_id": user_id,
                "scopes": scopes,
                "client_id": token_info.get("client_id"),
                "token_info": token_info,
            }
        else:
            # IdentityServer authentication disabled - decode token locally without validation
            logger.info(
                "IdentityServer authentication disabled - Decoding token locally without validation"
            )
            payload = jwt.decode(
                token,
                SECRET_KEY,
                algorithms=[ALGORITHM],
                options={
                    "verify_signature": False,
                    "verify_aud": False,
                    "verify_iss": False,
                    "verify_exp": False,
                    "verify_at_hash": False,
                },
            )
            logger.debug(f"JWT decoded successfully. Payload keys: {payload.keys()}")

            user_id = (
                payload.get("UserId") or payload.get("sub") or payload.get("user_id")
            )
            logger.debug(f"Extracted UserId from token: {user_id}")

            if user_id is None:
                logger.error("UserId is None, raising credentials exception")
                raise credentials_exception
            logger.debug(
                f"Authenticated user (local decode): {user_id}, type: {type(user_id)}"
            )
            return {
                "user_id": user_id,
                "scopes": (
                    payload.get("scope", "").split()
                    if isinstance(payload.get("scope"), str)
                    else []
                ),
                "client_id": payload.get("client_id"),
                "token_info": payload,
            }
    except JWTError as e:
        logger.error(f"JWT decode error: {str(e)}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise credentials_exception
