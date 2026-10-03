from django.http import HttpResponseRedirect
from allauth.core.exceptions import ImmediateHttpResponse  # allauth.exceptions on older versions
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter

FRONTEND_CALLBACK = "https://koshh.me/oauth/callback"

def _redirect(error):
    raise ImmediateHttpResponse(
        HttpResponseRedirect(f"{FRONTEND_CALLBACK}?error={error}")
    )


class KoshSocialAccountAdapter(DefaultSocialAccountAdapter):
    def save_user(self, request, sociallogin, form=None):
        user = super().save_user(request, sociallogin, form)
        name = f"{user.first_name} {user.last_name}".strip()
        if not name:
            name = (sociallogin.account.extra_data.get("name") or "").strip()
        if name:
            user.profile.name = name[:50]  # Profile.name has max_length=50
            user.profile.save(update_fields=["name"])
        return user
    def is_auto_signup_allowed(self, request, sociallogin):
        if not any(e.verified for e in sociallogin.email_addresses):
            _redirect("email_not_verified")
        return True
    def on_authentication_error(self, request, provider, error=None,exception=None, extra_context=None):
        provider_id = getattr(provider, "id", provider) or "oauth"
        _redirect(f"{provider_id}_login_failed")
