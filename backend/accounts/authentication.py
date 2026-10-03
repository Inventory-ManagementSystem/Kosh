from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import AuthenticationFailed
from drf_spectacular.extensions import OpenApiAuthenticationExtension

class TokenVersionJWTAuthentication(JWTAuthentication):

    def get_user(self, validated_token):
        user=super().get_user(validated_token)
        token_version=validated_token.get("token_version")

        if token_version is None:
            raise AuthenticationFailed("Invalid token")
        if token_version!=user.profile.token_version:
            raise AuthenticationFailed("Token is no longer valid.")

        return user


class TokenVersionJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    target_class = "accounts.authentication.TokenVersionJWTAuthentication"
    name = "BearerAuth"
    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
