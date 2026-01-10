from django.shortcuts import render, redirect
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import Prefetch
from django.http import JsonResponse
from decimal import Decimal, InvalidOperation
import json

from .models import Portfolio, Stock, StockPrice
from .services import PortfolioService, StockTransactionService, StockDataService

MIN_VALUE_DIFF = Decimal("0.01")
SHARES_Q = Decimal("0.00000001")
MONEY_Q = Decimal("0.01")
MIN_SHARES_LEFT = Decimal("0.0001")

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
    if request.method == 'POST' and 'add_funds' in request.POST:
        try:
            amount = Decimal(request.POST.get('amount', 0))
            PortfolioService.add_funds(portfolio_id, amount)
            messages.success(request, f'Se agregaron ${amount:,.2f} al portafolio exitosamente.')
        except ValueError as e:
            messages.error(request, str(e))
        except (InvalidOperation, TypeError):
            messages.error(request, 'Monto inválido.')
        return redirect('portfolio_detail', portfolio_id=portfolio_id)
    
    if request.method == 'POST' and 'update_allocations' in request.POST:
        try:
            PortfolioService.update_allocations(portfolio_id, request.POST)
            messages.success(request, 'Target allocations actualizadas exitosamente.')
        except ValueError as e:
            messages.error(request, str(e))
        except Exception as e:
            messages.error(request, f'Error al actualizar allocations: {str(e)}')
        return redirect('portfolio_detail', portfolio_id=portfolio_id)
    
    try:
        data = PortfolioService.get_portfolio_with_holdings(portfolio_id)
        allocations = data['portfolio'].allocations.select_related('stock').all()
        
        return render(request, 'portfolio_detail.html', {
            'portfolio': data['portfolio'],
            'holdings_data': data['holdings_data'],
            'total_portfolio_value': data['total_portfolio_value'],
            'allocations': allocations
        })
    except Exception as e:
        messages.error(request, f'Error al cargar portfolio: {str(e)}')
        return redirect('home')

def get_portfolio_balance(request, portfolio_id):
    try:
        data = PortfolioService.get_balance(portfolio_id)
        return JsonResponse({
            'success': True,
            **data
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
        
        result = StockTransactionService.buy_stock(
            portfolio_id=portfolio_id,
            stock_id=stock_id,
            shares=shares
        )
        
        return JsonResponse({
            'success': True,
            'message': f'Compra exitosa: {result["total_shares"]} acciones de {result["stock_symbol"]} por ${result["total_cost"]:.2f}',
            'new_balance': float(result['new_balance']),
            'total_shares': float(result['total_shares']),
            'average_price': float(result['average_price'])
        })
        
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error al procesar la compra: {str(e)}'
        }, status=500)

def sell_stock(request):
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
        
        result = StockTransactionService.sell_stock(
            portfolio_id=portfolio_id,
            stock_id=stock_id,
            shares=shares
        )
        
        message = f'Venta exitosa: {result["remaining_shares"]} acciones de {result["stock_symbol"]} por ${result["total_income"]:.2f}'
        if result['holding_deleted']:
            message = f'Venta exitosa de {result["stock_symbol"]} por ${result["total_income"]:.2f}. Holding eliminado (sin acciones restantes).'
        
        return JsonResponse({
            'success': True,
            'message': message,
            'new_balance': float(result['new_balance']),
            'remaining_shares': float(result['remaining_shares'])
        })
        
    except ValueError as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': f'Error al procesar la venta: {str(e)}'
        }, status=500)

def simulate_time(request):
    if request.method != 'POST':
        return redirect('home')
    
    try:
        amount = request.POST.get('amount', 1)
        unit = request.POST.get('unit', 'days')
        
        result = StockDataService.simulate_time_forward(amount, unit)
        
        messages.success(
            request,
            f'Simulación completada: {result["total_days"]} día(s) simulado(s) para {result["stocks_count"]} acción(es). '
            f'Se crearon {result["prices_created"]} nuevos registros de precios.'
        )
        return redirect('home')
        
    except ValueError as e:
        messages.error(request, str(e))
        return redirect('home')
    except Exception as e:
        messages.error(request, f'Error al simular: {str(e)}')
        return redirect('home')

def stock_detail(request, stock_id):
    try:
        end_date = request.GET.get('end_date')
        start_date = request.GET.get('start_date')
        
        data = StockDataService.get_stock_price_history(
            stock_id=stock_id,
            start_date=start_date,
            end_date=end_date
        )
        
        return render(request, 'stock_detail.html', {
            'stock': data['stock'],
            'chart_data_json': json.dumps(data['chart_data']),
            'stats': data['stats'],
            'start_date': data['start_date'],
            'end_date': data['end_date'],
            'data_points': data['data_points']
        })
    except Exception as e:
        messages.error(request, f'Error al cargar datos del stock: {str(e)}')
        return redirect('home')


def rebalance_portfolio(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "error": "Método no permitido"}, status=405)

    try:
        portfolio_id = request.POST.get("portfolio_id")
        if not portfolio_id:
            return JsonResponse({"success": False, "error": "portfolio_id es requerido"}, status=400)

        if request.POST.get("confirm") == "true":
            result = PortfolioService.rebalance_portfolio(portfolio_id)
            return JsonResponse({"success": True, "data": result})
        
        result = PortfolioService.get_info_to_rebalance_portafolio(portfolio_id)
        return JsonResponse({"success": True, "data": result})

    except ValueError as e:
        return JsonResponse({"success": False, "error": str(e)}, status=400)
    except Exception as e:
        return JsonResponse({"success": False, "error": f"Error al rebalancear: {str(e)}"}, status=500)

