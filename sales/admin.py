from django.contrib import admin
from .models import (
    ExchangeRate, Brand, DailySalesTotal, DailySalesB2B,
    DailySalesB2C, BrandDailySales, ShopifyOrder, TiktokOrder,
    ShopeeOrder, Qoo10Order, TaxByState
)


@admin.register(ExchangeRate)
class ExchangeRateAdmin(admin.ModelAdmin):
    list_display = ('region', 'year', 'month', 'rate')
    list_filter = ('region', 'year')


@admin.register(Brand)
class BrandAdmin(admin.ModelAdmin):
    list_display = ('region', 'code', 'name', 'name_kr')
    list_filter = ('region',)


@admin.register(DailySalesTotal)
class DailySalesTotalAdmin(admin.ModelAdmin):
    list_display = ('region', 'date', 'gmv', 'gsv', 'cogs', 'total_expense', 'operating_profit', 'operating_margin')
    list_filter = ('region', 'year', 'month')
    date_hierarchy = 'date'


@admin.register(DailySalesB2B)
class DailySalesB2BAdmin(admin.ModelAdmin):
    list_display = ('region', 'date', 'sales_total', 'sales_us', 'operating_profit')
    list_filter = ('region', 'year', 'month')


@admin.register(DailySalesB2C)
class DailySalesB2CAdmin(admin.ModelAdmin):
    list_display = ('region', 'date', 'b2c_total', 'shopify', 'amazon', 'tiktok', 'shopee', 'qoo10', 'gsv', 'operating_profit')
    list_filter = ('region', 'year', 'month')


@admin.register(BrandDailySales)
class BrandDailySalesAdmin(admin.ModelAdmin):
    list_display = ('region', 'date', 'brand', 'b2c_total', 'gsv', 'total_gsv')
    list_filter = ('region', 'brand', 'year', 'month')
    date_hierarchy = 'date'


@admin.register(ShopifyOrder)
class ShopifyOrderAdmin(admin.ModelAdmin):
    list_display = ('region', 'order_date', 'brand', 'order_name', 'final_amount', 'lineitem_name')
    list_filter = ('region', 'brand', 'financial_status')
    search_fields = ('order_name', 'email', 'lineitem_name')


@admin.register(TiktokOrder)
class TiktokOrderAdmin(admin.ModelAdmin):
    list_display = ('region', 'order_date', 'brand', 'order_id', 'final_amount', 'product_name')
    list_filter = ('region', 'brand', 'order_status')
    search_fields = ('order_id', 'product_name')


@admin.register(ShopeeOrder)
class ShopeeOrderAdmin(admin.ModelAdmin):
    list_display = ('region', 'order_date', 'brand', 'order_id', 'final_amount', 'product_name')
    list_filter = ('region', 'brand', 'order_status')
    search_fields = ('order_id', 'product_name')


@admin.register(Qoo10Order)
class Qoo10OrderAdmin(admin.ModelAdmin):
    list_display = ('region', 'order_date', 'brand', 'order_id', 'final_amount', 'product_name')
    list_filter = ('region', 'brand', 'order_status')
    search_fields = ('order_id', 'product_name')


@admin.register(TaxByState)
class TaxByStateAdmin(admin.ModelAdmin):
    list_display = ('region', 'state_code', 'year', 'month', 'amount')
    list_filter = ('region', 'year', 'month')
