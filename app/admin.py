from django.contrib import admin
from .models import Portfolio, Stock, Holding, TargetAllocation, StockPrice

# Register your models here.
admin.site.register(Portfolio)
admin.site.register(Stock)
admin.site.register(Holding)
admin.site.register(TargetAllocation)
admin.site.register(StockPrice)
