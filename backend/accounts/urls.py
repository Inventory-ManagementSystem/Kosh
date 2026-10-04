from django.urls import path
from . import views



urlpatterns = [
  path('register/',views.RegisterApi.as_view(),name='register_api'),
  path('login/',views.LoginApi.as_view(),name='login_api'),
  path('token/refresh/',views.CookieTokenRefreshView.as_view(),name='token_refresh'),
  path('profile/',views.ProfileApi.as_view(),name='profile_api'),
  path('logout/',views.LogoutApi.as_view(),name='logout_api'),
  path('forgot-password/', views.ForgotPasswordApi.as_view(), name="forgot-password"),
  path('verify-reset-otp/', views.VerifyResetOTPApi.as_view(), name="verify-reset-otp"),
  path('reset-password/', views.ResetPasswordApi.as_view(), name="reset-password"),
  path('change-password/', views.ChangePasswordApi.as_view(), name="change-password"),

  path('google/jwt/',views.GoogleJWTApi.as_view(),name='google_jwt'),
  path("github/jwt/", views.GitHubJWTApi.as_view(), name="github-jwt"),
  path("business/register/",views.BusinessRegistration.as_view(),name="business-register"),
  path("verify-registration-otp/",views.VerifyRegistrationOTPApi.as_view(), name="verify_registration_otp",),
  path("resend-registration-otp/", views.ResendRegistrationOTPApi.as_view(), name="resend-registration-otp"),
  path("employees/", views.EmployeeListApi.as_view(), name="employee-list"),
  path("employees/invite/", views.InviteEmployeeApi.as_view(), name="employee-invite"),
  path("employees/invites/<int:invite_id>/", views.CancelInviteApi.as_view(), name="invite-cancel"),
  path("employees/<int:employee_id>/", views.RemoveEmployeeApi.as_view(), name="employee-remove"),
  path("invites/mine/", views.MyInvitesApi.as_view(), name="my-invites"),
  path("invites/<int:invite_id>/accept/", views.AcceptInviteApi.as_view(), name="invite-accept"),
  path("invites/<int:invite_id>/decline/", views.DeclineInviteApi.as_view(), name="invite-decline"),
  
]
