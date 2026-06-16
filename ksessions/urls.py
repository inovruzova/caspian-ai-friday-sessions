from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('sessions/', views.sessions_view, name='sessions'),
    path('apply/', views.apply_view, name='apply'),
    path('rules/', views.rules_view, name='rules'),
    path('notifications/', views.notifications_view, name='notifications'),
]