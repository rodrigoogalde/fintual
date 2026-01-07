from django.shortcuts import render, HttpResponse, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Prefetch
from .models import Portfolio, Stock, Holding, TargetAllocation, StockPrice

# Create your views here.
def home(request):
    portfolios_list = Portfolio.objects.all()
    portfolios_paginator = Paginator(portfolios_list, 10)
    portfolios_page = request.GET.get('portfolios_page', 1)
    portfolios = portfolios_paginator.get_page(portfolios_page)
    
    stocks_list = Stock.objects.prefetch_related(
        Prefetch('prices', queryset=StockPrice.objects.order_by('-date')[:1], to_attr='latest_price')
    ).all()
    stocks_paginator = Paginator(stocks_list, 20)
    stocks_page = request.GET.get('stocks_page', 1)
    stocks = stocks_paginator.get_page(stocks_page)
    
    return render(request, 'home.html', {
        'portfolios': portfolios,
        'stocks': stocks
    })

def portfolio_detail(request, portfolio_id):
    portfolio = get_object_or_404(Portfolio, id=portfolio_id)
    holdings = portfolio.holdings.select_related('stock').all()
    allocations = portfolio.allocations.select_related('stock').all()
    
    return render(request, 'portfolio_detail.html', {
        'portfolio': portfolio,
        'holdings': holdings,
        'allocations': allocations
    })
