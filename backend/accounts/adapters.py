from django.http import HttpResponseRedirect
from allauth.exceptions import ImmediateHttpResponse
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter


class KoshSocialAccountAdapter(DefaultSocialAccountAdapter):
  def on_authentication_error(
    self,
    request,
    provider,
    error=None,
    exception=None,
    extra_context=None,
  ):
    raise ImmediateHttpResponse(
      HttpResponseRedirect(
        "https://koshh.me/oauth/callback?error=google_login_failed"
      )
    )