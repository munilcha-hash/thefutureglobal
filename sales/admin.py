from django.contrib import admin
from .models import (
    ExchangeRate, Brand, DailySalesTotal, DailySalesB2B,
    DailySalesB2C, BrandDailySales, ShopifyOrder, TiktokOrder, TaxByState
)


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('year', 'month', 'rate')


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'name_kr')


@admin.register(DailySalesTotal)
class DailySalesTotalAdmin(admin.ModelAdmin):
    list_display = ('date', 'gmv', 'gsv', 'cogs', 'total_expense', 'operating_profit', 'operating_margin')
    list_filter = ('year', 'month')
    date_hierarchy = 'date'


@admin.register(DailySalesB2B)
class DailySalesB2BAdmin(admin.ModelAdmin):
    list_display = ('date', 'sales_total', 'sales_us', 'operating_profit')
    list_filter = ('year', 'month')


@admin.register(DailySalesB2C)
class DailySalesB2CAdmin(admin.ModelAdmin):
    list_display = ('date', 'b2c_total', 'shopify', 'amazon', 'tiktok', 'gsv', 'operating_profit')
    list_filter = ('year', 'month')


@admin.register(BrandDailySales)
class BrandDailySalesAdmin(admin.ModelAdmin):
    list_display = ('date', 'brand', 'b2c_total', 'gsv', 'total_gsv')
    list_filter = ('brand', 'year', 'month')
    date_hierarchy = 'date'


@admin.register(ShopifyOrder)
class ShopifyOrderAdmin(admin.ModelAdmin):
    list_display = ('order_date', 'brand', 'order_name', 'final_amount', 'lineitem_name')
    list_filter = ('brand', 'financial_status')
    search_fields = ('order_name', 'email', 'lineitem_name')


@admin.register(TiktokOrder)
class TiktokOrderAdmin(admin.ModelAdmin):
    list_display = ('order_date', 'brand', 'order_id', 'final_amount', 'product_name')
    list_filter = ('brand', 'order_status')
    search_fields = ('order_id', 'product_name')


@admin.register(TaxByState)
class TaxByStateAdmin(admin.ModelAdmin):
    list_display = ('state_code', 'year', 'month', 'amount')
    list_filter = ('year', 'month')
