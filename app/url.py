from django.urls import path
from .views import home, portfolio_detail

urlpatterns = [
    path('', home, name='home'),
    path('portfolio/<int:portfolio_id>/', portfolio_detail, name='portfolio_detail'),
]