import csv
from decimal import Decimal, InvalidOperation
from datetime import date
from django.core.management.base import BaseCommand
from app.models import Stock, StockPrice


class Command(BaseCommand):
    help = 'Seed stocks and initial prices from NASDAQ CSV file'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv-path',
            type=str,
            default='data/nasdaq_screener.csv',
            help='Path to the NASDAQ CSV file (relative to project root)'
        )

    def handle(self, *args, **options):
        csv_path = options['csv_path']
        
        self.stdout.write(self.style.WARNING(f'Reading CSV from: {csv_path}'))
        
        # Para no crear demasiados stocks en una sola corrida
        total_stocks_to_create = 100
        stocks_created = 0
        prices_created = 0
        stocks_skipped = 0
        
        try:
            with open(csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                for row in reader:
                    symbol = row.get('Symbol', '').strip()
                    name = row.get('Name', '').strip()
                    last_sale = row.get('Last Sale', '').strip()
                    volume_str = row.get('Volume', '').strip()
                    
                    if not symbol:
                        continue
                    
                    stock, created = Stock.objects.get_or_create(
                        symbol=symbol,
                        defaults={'name': name}
                    )
                    
                    if created:
                        stocks_created += 1
                        self.stdout.write(f'Created stock: {symbol} - {name}')
                    else:
                        stocks_skipped += 1
                    
                    try:
                        if last_sale and last_sale.startswith('$'):
                            price = Decimal(last_sale.replace('$', '').replace(',', ''))
                        else:
                            price = None
                    except (InvalidOperation, ValueError):
                        price = None
                    
                    try:
                        volume = int(volume_str.replace(',', '')) if volume_str else None
                    except ValueError:
                        volume = None
                    
                    if price is not None:
                        stock_price, price_created = StockPrice.objects.get_or_create(
                            stock=stock,
                            date=date.today(),
                            defaults={
                                'price': price,
                                'volume': volume
                            }
                        )
                        
                        if price_created:
                            prices_created += 1
        
                    if stocks_created >= total_stocks_to_create:
                        break

        except FileNotFoundError:
            self.stdout.write(
                self.style.ERROR(f'CSV file not found: {csv_path}')
            )
            return
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error processing CSV: {str(e)}')
            )
            return
        
        # Summary
        self.stdout.write(self.style.SUCCESS('\n' + '='*50))
        self.stdout.write(self.style.SUCCESS(f'Stocks created: {stocks_created}'))
        self.stdout.write(self.style.SUCCESS(f'Stocks skipped (already exist): {stocks_skipped}'))
        self.stdout.write(self.style.SUCCESS(f'Stock prices created: {prices_created}'))
        self.stdout.write(self.style.SUCCESS('='*50))
