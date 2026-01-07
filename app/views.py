from django.shortcuts import render, HttpResponse, get_object_or_404, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import JsonResponse
from django.db import transaction
from decimal import Decimal, InvalidOperation
from datetime import timedelta
import random
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

def simulate_time(request):
    if request.method != 'POST':
        return redirect('home')
    
    try:
        amount = int(request.POST.get('amount', 1))
        unit = request.POST.get('unit', 'days')
        
        if amount <= 0 or amount > 365:
            messages.error(request, 'La cantidad debe estar entre 1 y 365.')
            return redirect('home')
        
        days_map = {
            'days': 1,
            'weeks': 7,
            'months': 30
        }
        
        if unit not in days_map:
            messages.error(request, 'Unidad de tiempo inválida.')
            return redirect('home')
        
        total_days = amount * days_map[unit]
        
        if total_days > 365:
            messages.error(request, 'No se puede simular más de 365 días.')
            return redirect('home')
        
        with transaction.atomic():
            stocks_data = Stock.objects.values('id', 'symbol').all()
            stock_ids = [s['id'] for s in stocks_data]
            
            if not stock_ids:
                messages.warning(request, 'No hay acciones para simular.')
                return redirect('home')
            
            latest_prices = {}
            last_dates = {}
            
            for stock_id in stock_ids:
                last_price_obj = StockPrice.objects.filter(
                    stock_id=stock_id
                ).order_by('-date').values('date', 'price', 'volume').first()
                
                if last_price_obj and last_price_obj['price']:
                    latest_prices[stock_id] = float(last_price_obj['price'])
                    last_dates[stock_id] = last_price_obj['date']
            
            if not latest_prices:
                messages.warning(request, 'No hay precios históricos para simular.')
                return redirect('home')
            
            new_prices = []
            
            for stock_id in latest_prices.keys():
                current_price = latest_prices[stock_id]
                start_date = last_dates[stock_id]
                
                for day in range(1, total_days + 1):
                    change_percent = random.uniform(-0.03, 0.03)
                    
                    current_price = current_price * (1 + change_percent)
                    
                    new_date = start_date + timedelta(days=day)
                    
                    volume = random.randint(100000, 10000000)
                    
                    price_decimal = Decimal(str(round(current_price, 8)))
                    
                    new_prices.append(
                        StockPrice(
                            stock_id=stock_id,
                            date=new_date,
                            price=price_decimal,
                            volume=volume
                        )
                    )
            
            if new_prices:
                StockPrice.objects.bulk_create(
                    new_prices,
                    batch_size=5000,
                    ignore_conflicts=True
                )
                
                messages.success(
                    request,
                    f'Simulación completada: {total_days} día(s) simulado(s) para {len(latest_prices)} acción(es). '
                    f'Se crearon {len(new_prices)} nuevos registros de precios.'
                )
            else:
                messages.warning(request, 'No se generaron nuevos precios.')
        
        return redirect('home')
        
    except ValueError as e:
        messages.error(request, f'Error en los valores ingresados: {str(e)}')
        return redirect('home')
    except Exception as e:
        messages.error(request, f'Error al simular: {str(e)}')
        return redirect('home')

def stock_detail(request, stock_id):
    stock = get_object_or_404(Stock, id=stock_id)
    
    from datetime import datetime, timedelta
    
    end_date = request.GET.get('end_date')
    start_date = request.GET.get('start_date')
    
    if end_date:
        try:
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            end_date = None
    
    if start_date:
        try:
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        except ValueError:
            start_date = None
    
    if not end_date:
        latest_price = stock.prices.order_by('-date').first()
        end_date = latest_price.date if latest_price else datetime.now().date()
    
    if not start_date:
        start_date = end_date - timedelta(days=30)
    
    prices = stock.prices.filter(
        date__gte=start_date,
        date__lte=end_date
    ).order_by('date').values('date', 'price', 'volume')
    
    chart_data = {
        'labels': [p['date'].strftime('%Y-%m-%d') for p in prices],
        'prices': [float(p['price']) if p['price'] else 0 for p in prices],
        'volumes': [p['volume'] if p['volume'] else 0 for p in prices]
    }
    
    prices_list = [float(p['price']) for p in prices if p['price']]
    stats = {}
    if prices_list:
        stats = {
            'current_price': prices_list[-1] if prices_list else 0,
            'max_price': max(prices_list),
            'min_price': min(prices_list),
            'avg_price': sum(prices_list) / len(prices_list),
            'change': prices_list[-1] - prices_list[0] if len(prices_list) > 1 else 0,
            'change_percent': ((prices_list[-1] - prices_list[0]) / prices_list[0] * 100) if len(prices_list) > 1 and prices_list[0] != 0 else 0
        }
    
    import json
    
    return render(request, 'stock_detail.html', {
        'stock': stock,
        'chart_data_json': json.dumps(chart_data),
        'stats': stats,
        'start_date': start_date,
        'end_date': end_date,
        'data_points': len(prices)
    })
