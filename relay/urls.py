from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("login/", auth_views.LoginView.as_view(
        template_name="messaging/login.html", redirect_authenticated_user=True
    ), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("messaging.urls")),
]
