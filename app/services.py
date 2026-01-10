from decimal import Decimal
from django.shortcuts import get_object_or_404
from django.db import transaction
from .models import Portfolio, Stock, Holding, TargetAllocation, StockPrice
from datetime import timedelta
import random
from decimal import InvalidOperation
from datetime import datetime, timedelta

class PortfolioService:
    @staticmethod
    def get_portfolio_with_holdings(portfolio_id: int) -> dict:
        portfolio = get_object_or_404(Portfolio, id=portfolio_id)
        holdings = portfolio.holdings.select_related('stock').prefetch_related('stock__prices').all()
        
        total_portfolio_value = Decimal('0')
        holdings_data = []
        
        for holding in holdings:
            latest_price = holding.stock.prices.order_by('-date').first()
            current_price = latest_price.price if latest_price and latest_price.price else Decimal('0')
            
            holding_value = holding.shares * current_price
            total_portfolio_value += holding_value
            
            holdings_data.append({
                'holding': holding,
                'value': holding_value,
                'current_price': current_price
            })
        
        for data in holdings_data:
            if total_portfolio_value > 0:
                data['percentage'] = (data['value'] / total_portfolio_value) * 100
            else:
                data['percentage'] = 0
        
        return {
            'portfolio': portfolio,
            'holdings_data': holdings_data,
            'total_portfolio_value': total_portfolio_value
        }
    
    @staticmethod
    def get_balance(portfolio_id: int) -> dict:
        portfolio = get_object_or_404(Portfolio, id=portfolio_id)
        return {
            'balance': float(portfolio.cash_balance),
            'portfolio_name': portfolio.name
        }
    
    @staticmethod
    def add_funds(portfolio_id: int, amount: Decimal) -> Portfolio:
        if amount <= 0:
            raise ValueError('El monto debe ser mayor a 0')
        
        portfolio = get_object_or_404(Portfolio, id=portfolio_id)
        portfolio.cash_balance += amount
        portfolio.save()
        
        return portfolio
    
    @staticmethod
    def update_allocations(portfolio_id: int, post_data: dict) -> bool:
        portfolio = get_object_or_404(Portfolio, id=portfolio_id)
        allocations = portfolio.allocations.all()
        
        total_percent = Decimal('0')
        updates = []
        
        for allocation in allocations:
            percent_key = f'target_percent_{allocation.id}'
            percent_value = post_data.get(percent_key, '0')
            
            try:
                percent = Decimal(percent_value)
            except (ValueError, Exception):
                raise ValueError(f'Porcentaje inválido para {allocation.stock.symbol}')
            
            if percent < 0:
                raise ValueError(f'El porcentaje para {allocation.stock.symbol} no puede ser negativo')
            
            total_percent += percent
            updates.append((allocation, percent))
        
        if total_percent != 100:
            raise ValueError(f'La suma de los porcentajes debe ser 100%. Actual: {total_percent}%')
        
        with transaction.atomic():
            for allocation, percent in updates:
                allocation.target_percent = float(percent)
                allocation.save()
        return True
    
    @staticmethod
    def _latest_price(stock: Stock) -> Decimal:
        prices = getattr(stock, "prices_cache", None)
        if prices is not None:
            return prices[0].price if prices else None
        lp = stock.prices.order_by("-date").first()
        return lp.price if lp and lp.price is not None else None
    
    @staticmethod
    def _cache_prices_for_stock(stock: Stock) -> None:
        prices = list(stock.prices.all())
        prices.sort(key=lambda p: p.date, reverse=True)
        stock.prices_cache = prices
    
    @staticmethod
    def get_info_to_rebalance_portafolio(portfolio_id: int) -> dict:
        portfolio = get_object_or_404(Portfolio, id=portfolio_id)
        # Obtener holdings y allocations
        holdings = list(
            portfolio.holdings
            .select_related("stock")
            .prefetch_related("stock__prices")
            .all()
        )
        allocations = list(
            portfolio.allocations
            .select_related("stock")
            .prefetch_related("stock__prices")
            .all()
        )
        
        # Cachear precios
        for h in holdings:
            PortfolioService._cache_prices_for_stock(h.stock)
        for a in allocations:
            PortfolioService._cache_prices_for_stock(a.stock)
        
        # Dejamos las allocations en un dict para acceso rápido
        allocations_dict = {}
        for a in allocations:
            allocations_dict[a.stock.symbol] = a
        
        total_invested = Decimal("0")
        
        # Hacemos un loop para obtener los valores de cada stock en el portafolio, calcular su valor y obtener el valor total del portafolio
        for holding in holdings:
            allocation = allocations_dict.get(holding.stock.symbol)
            latest_price = PortfolioService._latest_price(holding.stock)
            value = holding.shares * latest_price if latest_price else Decimal("0")
            holding.current_value = value
            holding.allocation_expected_percent = Decimal(str(allocation.target_percent)) if allocation else Decimal("0")
            total_invested += value
        
        # Una vez obtenido el valor total, hacemos otro loop para calcular el porcentaje actual, valor objetivo, delta y acciones a comprar/vender
        for holding in holdings:
            holding.allocation_current_percent = (
                (holding.current_value / total_invested * Decimal("100")) 
                if total_invested > 0 else Decimal("0")
            )
            objetive_value = (holding.allocation_expected_percent / Decimal("100")) * total_invested
            delta_value = objetive_value - holding.current_value
            stocks_to_buy_sell = (
                delta_value / PortfolioService._latest_price(holding.stock) 
                if PortfolioService._latest_price(holding.stock) else Decimal("0")
            )
            
            holding.objective_value = objetive_value
            holding.delta_value = delta_value
            holding.stocks_to_buy_sell = stocks_to_buy_sell
        
        # Finalmente, creamos las estructuras de datos para retornarlos
        holdings_data = [{
            "stock_symbol": holding.stock.symbol,
            "stock_name": holding.stock.name,
            "shares": float(holding.shares),
            "current_value": float(holding.current_value),
            "allocation_expected_percent": float(holding.allocation_expected_percent),
            "allocation_current_percent": float(holding.allocation_current_percent),
            "objective_value": float(holding.objective_value),
            "delta_value": float(holding.delta_value),
            "stocks_to_buy_sell": float(holding.stocks_to_buy_sell),
        } for holding in holdings]
        
        allocations_data = [{
            "stock_symbol": allocation.stock.symbol,
            "stock_name": allocation.stock.name,
            "target_percent": float(allocation.target_percent),
        } for allocation in allocations]
        
        return {
            "total_invested": float(total_invested),
            "cash_balance": float(portfolio.cash_balance),
            "holdings": holdings_data,
            "allocations": allocations_data,
        }

    @staticmethod
    def rebalance_portfolio(portfolio_id: int) -> dict:
        # Utilizamos la info obtenida para el rebalanceo
        info = PortfolioService.get_info_to_rebalance_portafolio(portfolio_id)
        portfolio = get_object_or_404(Portfolio, id=portfolio_id)
        
        operations_to_sell = []
        operations_to_buy = []
        
        # Recorremos los stocks del portafolio para separar las operaciones de compra y venta
        for holding in info['holdings']:
            stocks_to_trade = Decimal(str(holding['stocks_to_buy_sell']))
            
            stock = Stock.objects.get(symbol=holding['stock_symbol'])
            PortfolioService._cache_prices_for_stock(stock)
            current_price = PortfolioService._latest_price(stock)
            
            if current_price is None or current_price <= 0:
                raise ValueError(f'No hay precio válido para {holding["stock_symbol"]}')

            if stocks_to_trade < 0:
                shares_to_sell = abs(stocks_to_trade)
                operations_to_sell.append({
                    'stock': stock,
                    'shares': shares_to_sell,
                    'price': current_price,
                    'total': shares_to_sell * current_price
                })
            elif stocks_to_trade > 0:
                operations_to_buy.append({
                    'stock': stock,
                    'shares': stocks_to_trade,
                    'price': current_price,
                    'total': stocks_to_trade * current_price
                })
        
        total_from_sales = sum(op['total'] for op in operations_to_sell)
        total_for_purchases = sum(op['total'] for op in operations_to_buy)
        
        available_funds = portfolio.cash_balance + total_from_sales
        
        # Verificamos si hay fondos suficientes para las compras
        if available_funds < total_for_purchases:
            raise ValueError(
                f'Fondos insuficientes para rebalancear. '
                f'Disponible (incluyendo ventas): ${available_funds:.2f}, '
                f'Necesario: ${total_for_purchases:.2f}'
            )
        
        operations_log = []
        
        # Guardamos las operaciones en la base de datos
        with transaction.atomic():
            for op in operations_to_sell:
                try:
                    result = StockTransactionService.sell_stock(
                        portfolio_id=portfolio_id,
                        stock_id=op['stock'].id,
                        shares=op['shares']
                    )
                    operations_log.append(
                        f"Vendidas {op['shares']:.4f} acciones de {op['stock'].symbol} "
                        f"a ${op['price']:.2f} = ${result['total_income']:.2f}"
                    )
                except Exception as e:
                    raise ValueError(f"Error vendiendo {op['stock'].symbol}: {str(e)}")
            
            for op in operations_to_buy:
                try:
                    result = StockTransactionService.buy_stock(
                        portfolio_id=portfolio_id,
                        stock_id=op['stock'].id,
                        shares=op['shares']
                    )
                    operations_log.append(
                        f"Compradas {op['shares']:.4f} acciones de {op['stock'].symbol} "
                        f"a ${op['price']:.2f} = ${result['total_cost']:.2f}"
                    )
                except Exception as e:
                    raise ValueError(f"Error comprando {op['stock'].symbol}: {str(e)}")
        
        portfolio.refresh_from_db()
        
        return {
            'operations': operations_log,
            'total_sold': float(total_from_sales),
            'total_bought': float(total_for_purchases),
            'new_balance': float(portfolio.cash_balance),
            'operations_count': len(operations_log)
        }

class StockTransactionService:
    @staticmethod
    def _validate_and_convert_shares(shares: any) -> Decimal:
        
        if isinstance(shares, Decimal):
            shares_decimal = shares
        else:
            try:
                shares_decimal = Decimal(str(shares))
            except (InvalidOperation, ValueError, TypeError):
                raise ValueError('Cantidad de acciones inválida')
        
        if shares_decimal <= 0:
            raise ValueError('La cantidad de acciones debe ser mayor a 0')
        
        return shares_decimal
    
    @staticmethod
    def buy_stock(portfolio_id: int, stock_id: int, shares: Decimal) -> dict:
        shares = StockTransactionService._validate_and_convert_shares(shares)
        
        portfolio = get_object_or_404(Portfolio, id=portfolio_id)
        stock = get_object_or_404(Stock, id=stock_id)
        
        latest_price = stock.prices.order_by('-date').first()
        if not latest_price or not latest_price.price:
            raise ValueError('No hay precio disponible para esta acción')
        
        total_cost = shares * latest_price.price
        
        if total_cost > portfolio.cash_balance:
            raise ValueError(
                f'Balance insuficiente. Necesitas ${total_cost:.2f} pero solo tienes ${portfolio.cash_balance:.2f}'
            )
        
        with transaction.atomic():
            holding, created = Holding.objects.get_or_create(
                portfolio=portfolio,
                stock=stock,
                defaults={'shares': 0, 'average_price': 0}
            )
            
            total_shares = holding.shares + shares
            total_value = (holding.shares * holding.average_price) + (shares * latest_price.price)
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
        
        return {
            'total_cost': total_cost,
            'new_balance': portfolio.cash_balance,
            'total_shares': holding.shares,
            'average_price': holding.average_price,
            'stock_symbol': stock.symbol
        }
    
    @staticmethod
    def sell_stock(portfolio_id: int, stock_id: int, shares: Decimal) -> dict:
        shares = StockTransactionService._validate_and_convert_shares(shares)
        
        portfolio = get_object_or_404(Portfolio, id=portfolio_id)
        stock = get_object_or_404(Stock, id=stock_id)
        
        try:
            holding = Holding.objects.get(portfolio=portfolio, stock=stock)
        except Holding.DoesNotExist:
            raise ValueError('No tienes acciones de esta compañía en tu portafolio')
        
        if shares > holding.shares:
            raise ValueError(f'No tienes suficientes acciones. Disponibles: {holding.shares}')
        
        latest_price = stock.prices.order_by('-date').first()
        if not latest_price or not latest_price.price:
            raise ValueError('No hay precio disponible para esta acción')
        
        total_income = shares * latest_price.price
        
        with transaction.atomic():
            holding.shares -= shares
            
            holding_deleted = False
            if holding.shares <= Decimal('0.0001'):
                holding.delete()
                holding_deleted = True
            else:
                holding.save()
            
            portfolio.cash_balance += total_income
            portfolio.save()
        
        return {
            'total_income': total_income,
            'new_balance': portfolio.cash_balance,
            'remaining_shares': Decimal('0') if holding_deleted else holding.shares,
            'stock_symbol': stock.symbol,
            'holding_deleted': holding_deleted
        }

class StockDataService:    
    @staticmethod
    def get_stock_price_history(stock_id: int, start_date: datetime.date = None, end_date: datetime.date = None) -> dict:        
        stock = get_object_or_404(Stock, id=stock_id)
        
        if end_date:
            if isinstance(end_date, str):
                try:
                    end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
                except ValueError:
                    end_date = None
        
        if start_date:
            if isinstance(start_date, str):
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
                'change_percent': ((prices_list[-1] - prices_list[0]) / prices_list[0] * 100) 
                    if len(prices_list) > 1 and prices_list[0] != 0 else 0
            }
        
        return {
            'stock': stock,
            'chart_data': chart_data,
            'stats': stats,
            'start_date': start_date,
            'end_date': end_date,
            'data_points': len(prices)
        }
    
    @staticmethod
    def simulate_time_forward(amount: int, unit: str) -> dict:        
        try:
            amount = int(amount)
        except (ValueError, TypeError):
            raise ValueError('La cantidad debe ser un número entero')
        
        if amount <= 0 or amount > 365:
            raise ValueError('La cantidad debe estar entre 1 y 365')
        
        days_map = {
            'days': 1,
            'weeks': 7,
            'months': 30
        }
        
        if unit not in days_map:
            raise ValueError('Unidad de tiempo inválida')
        
        total_days = amount * days_map[unit]
        
        if total_days > 365:
            raise ValueError('No se puede simular más de 365 días')
        
        stocks_data = Stock.objects.values('id', 'symbol').all()
        stock_ids = [s['id'] for s in stocks_data]
        
        if not stock_ids:
            raise ValueError('No hay acciones para simular')
        
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
            raise ValueError('No hay precios históricos para simular')
        
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
            with transaction.atomic():
                StockPrice.objects.bulk_create(
                    new_prices,
                    batch_size=5000,
                    ignore_conflicts=True
                )
        else:
            raise ValueError('No se generaron nuevos precios')
        
        return {
            'total_days': total_days,
            'stocks_count': len(latest_prices),
            'prices_created': len(new_prices)
        }
