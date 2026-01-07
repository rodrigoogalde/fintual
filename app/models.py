from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class Portfolio(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name="portfolios")
    name = models.CharField(max_length=200)
    cash_balance = models.DecimalField(max_digits=20, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} - {self.owner.username}"

class Stock(models.Model):
    symbol = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.symbol

class Holding(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="holdings")
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    shares = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    average_price = models.DecimalField(max_digits=20, decimal_places=8, default=0)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['portfolio', 'stock'],
                name='unique_portfolio_stock'
            )
        ]

    def __str__(self):
        return f"{self.portfolio.name} — {self.stock.symbol}: {self.shares}"

class TargetAllocation(models.Model):
    portfolio = models.ForeignKey(Portfolio, on_delete=models.CASCADE, related_name="allocations")
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE)
    target_percent = models.FloatField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['portfolio', 'stock'],
                name='unique_portfolio_stock_allocation'
            )
        ]

    def __str__(self):
        return f"{self.stock.symbol} -> {self.target_percent * 100}% in {self.portfolio.name}"

class StockPrice(models.Model):
    stock = models.ForeignKey(Stock, on_delete=models.CASCADE, related_name="prices")
    date = models.DateField()
    price = models.DecimalField(max_digits=20, decimal_places=8, null=True, blank=True)
    volume = models.BigIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['stock', 'date'],
                name='unique_stock_date'
            )
        ]
        ordering = ['-date']

    def __str__(self):
        return f"{self.stock.symbol} - {self.date}: ${self.price}"
