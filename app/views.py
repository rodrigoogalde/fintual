from django.shortcuts import render, HttpResponse, get_object_or_404
from .models import Portfolio, Stock, Holding, TargetAllocation

# Create your views here.
def home(request):
    portfolios = Portfolio.objects.all()
    stocks = Stock.objects.all()
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
