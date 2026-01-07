from django.shortcuts import render, HttpResponse, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import JsonResponse
from decimal import Decimal, InvalidOperation
from .models import Portfolio, Stock, Holding, TargetAllocation, StockPrice

def home(request):
    portfolios_list = Portfolio.objects.all()
    portfolios_paginator = Paginator(portfolios_list, 10)
    portfolios_page = request.GET.get('portfolios_page', 1)
    portfolios = portfolios_paginator.get_page(portfolios_page)
    
    stocks_list = Stock.objects.prefetch_related(
        Prefetch('prices', queryset=StockPrice.objects.order_by('-date')[:1], to_attr='latest_price')
    ).all()
    stocks_paginator = Paginator(stocks_list, 10)
    stocks_page = request.GET.get('stocks_page', 1)
    stocks = stocks_paginator.get_page(stocks_page)
    
    return render(request, 'home.html', {
        'portfolios': portfolios,
        'stocks': stocks
    })

def portfolio_detail(request, portfolio_id):
    portfolio = get_object_or_404(Portfolio, id=portfolio_id)
    
    if request.method == 'POST' and 'add_funds' in request.POST:
        try:
            amount = Decimal(request.POST.get('amount', 0))
            if amount > 0:
                portfolio.cash_balance += amount
                portfolio.save()
                messages.success(request, f'Se agregaron ${amount:,.2f} al portafolio exitosamente.')
            else:
                messages.error(request, 'El monto debe ser mayor a 0.')
        except (ValueError, InvalidOperation):
            messages.error(request, 'Monto inválido.')
        return redirect('portfolio_detail', portfolio_id=portfolio.id)
    
    if request.method == 'POST' and 'update_allocations' in request.POST:
        try:
            allocations = portfolio.allocations.all()
            total_percent = Decimal('0')
            updates = []
            
            for allocation in allocations:
                percent_key = f'target_percent_{allocation.id}'
                percent_value = request.POST.get(percent_key, '0')
                
                try:
                    percent = Decimal(percent_value)
                    if percent < 0:
                        messages.error(request, f'El porcentaje para {allocation.stock.symbol} no puede ser negativo.')
                        return redirect('portfolio_detail', portfolio_id=portfolio.id)
                    
                    total_percent += percent
                    updates.append((allocation, percent))
                except (ValueError, InvalidOperation):
                    messages.error(request, f'Porcentaje inválido para {allocation.stock.symbol}.')
                    return redirect('portfolio_detail', portfolio_id=portfolio.id)
            
            if total_percent != 100:
                messages.error(request, f'La suma de los porcentajes debe ser 100%. Actual: {total_percent}%')
                return redirect('portfolio_detail', portfolio_id=portfolio.id)
            
            for allocation, percent in updates:
                allocation.target_percent = float(percent)
                allocation.save()
            
            messages.success(request, 'Target allocations actualizadas exitosamente.')
            return redirect('portfolio_detail', portfolio_id=portfolio.id)
            
        except Exception as e:
            messages.error(request, f'Error al actualizar allocations: {str(e)}')
            return redirect('portfolio_detail', portfolio_id=portfolio.id)
    
    holdings = portfolio.holdings.select_related('stock').all()
    allocations = portfolio.allocations.select_related('stock').all()
    
    total_portfolio_value = Decimal('0')
    holdings_data = []
    
    for holding in holdings:
        holding_value = holding.shares * holding.average_price
        total_portfolio_value += holding_value
        holdings_data.append({
            'holding': holding,
            'value': holding_value
        })
    
    for data in holdings_data:
        if total_portfolio_value > 0:
            data['percentage'] = (data['value'] / total_portfolio_value) * 100
        else:
            data['percentage'] = 0
    
    return render(request, 'portfolio_detail.html', {
        'portfolio': portfolio,
        'holdings_data': holdings_data,
        'total_portfolio_value': total_portfolio_value,
        'allocations': allocations
    })

def get_portfolio_balance(request, portfolio_id):
    try:
        portfolio = get_object_or_404(Portfolio, id=portfolio_id)
        return JsonResponse({
            'success': True,
            'balance': float(portfolio.cash_balance),
            'portfolio_name': portfolio.name
        })
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)

def buy_stock(request):
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Método no permitido'}, status=405)
    
    try:
        portfolio_id = request.POST.get('portfolio_id')
        stock_id = request.POST.get('stock_id')
        shares = request.POST.get('shares')
        
        if not all([portfolio_id, stock_id, shares]):
            return JsonResponse({
                'success': False,
                'error': 'Todos los campos son requeridos'
            }, status=400)
        
        portfolio = get_object_or_404(Portfolio, id=portfolio_id)
        stock = get_object_or_404(Stock, id=stock_id)
        
        try:
            shares_decimal = Decimal(shares)
            if shares_decimal <= 0:
                return JsonResponse({
                    'success': False,
                    'error': 'La cantidad de acciones debe ser mayor a 0'
                }, status=400)
        except (InvalidOperation, ValueError):
            return JsonResponse({
                'success': False,
                'error': 'Cantidad de acciones inválida'
            }, status=400)
        
        latest_price = stock.prices.order_by('-date').first()
        if not latest_price or not latest_price.price:
            return JsonResponse({
                'success': False,
                'error': 'No hay precio disponible para esta acción'
            }, status=400)
        
        total_cost = shares_decimal * latest_price.price
        
        if total_cost > portfolio.cash_balance:
            return JsonResponse({
                'success': False,
                'error': f'Balance insuficiente. Necesitas ${total_cost:.2f} pero solo tienes ${portfolio.cash_balance:.2f}'
            }, status=400)
        
        holding, created = Holding.objects.get_or_create(
            portfolio=portfolio,
            stock=stock,
            defaults={'shares': 0, 'average_price': 0}
        )
        
        total_shares = holding.shares + shares_decimal
        total_value = (holding.shares * holding.average_price) + (shares_decimal * latest_price.price)
        new_average_price = total_value / total_shares if total_shares > 0 else latest_price.price
        
        holding.shares = total_shares
        holding.average_price = new_average_price
        holding.save()
        
        TargetAllocation.objects.get_or_create(
            portfolio=portfolio,
            stock=stock,
            defaults={'target_percent': 0.0}
        )
        
        portfolio.cash_balance -= total_cost
        portfolio.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Compra exitosa: {shares_decimal} acciones de {stock.symbol} por ${total_cost:.2f}',
            'new_balance': float(portfolio.cash_balance),
            'total_shares': float(holding.shares),
            'average_price': float(holding.average_price)
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error al procesar la compra: {str(e)}'
        }, status=500)
