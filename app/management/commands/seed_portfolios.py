from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from app.models import Portfolio
from decimal import Decimal


class Command(BaseCommand):
    help = 'Seed portfolios for existing users'

    def handle(self, *args, **options):
        portfolios_created = 0
        portfolios_skipped = 0
        
        self.stdout.write(self.style.WARNING('Creating portfolios for users...'))
        
        users = User.objects.all()
        
        if not users.exists():
            self.stdout.write(
                self.style.ERROR('No users found. Please create users first using seed_users command.')
            )
            return
        
        for user in users:
            portfolio_name = f"Portafolio de {user.username}"
            
            if Portfolio.objects.filter(owner=user, name=portfolio_name).exists():
                portfolios_skipped += 1
                self.stdout.write(
                    self.style.WARNING(f'Portfolio "{portfolio_name}" already exists for {user.username}, skipping...')
                )
                continue
            
            portfolio = Portfolio.objects.create(
                owner=user,
                name=portfolio_name,
                cash_balance=Decimal('10000.00')
            )
            
            portfolios_created += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f'Created portfolio: {portfolio_name} for {user.username} with ${portfolio.cash_balance}'
                )
            )
        
        self.stdout.write(self.style.SUCCESS('\n' + '='*50))
        self.stdout.write(self.style.SUCCESS(f'Portfolios created: {portfolios_created}'))
        self.stdout.write(self.style.SUCCESS(f'Portfolios skipped (already exist): {portfolios_skipped}'))
        self.stdout.write(self.style.SUCCESS('='*50))
