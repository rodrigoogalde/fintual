from django.urls import path
from .views import home, portfolio_detail, get_portfolio_balance, buy_stock

urlpatterns = [
    path('', home, name='home'),
    path('portfolio/<int:portfolio_id>/', portfolio_detail, name='portfolio_detail'),
    path('api/portfolio/<int:portfolio_id>/balance/', get_portfolio_balance, name='get_portfolio_balance'),
    path('api/buy-stock/', buy_stock, name='buy_stock'),
]