import json
from decimal import Decimal
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.db.models import Sum, Avg, Count, F
from django.contrib import messages
from django.core.management import call_command
from .models import (
    ExchangeRate, Brand, DailySalesTotal, DailySalesB2B,
    DailySalesB2C, BrandDailySales, ShopifyOrder, TiktokOrder, TaxByState
)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _get_available_months():
    months = DailySalesTotal.objects.values('year', 'month').distinct().order_by('year', 'month')
    return list(months)


def dashboard(request):
    """메인 대시보드"""
    months = _get_available_months()
    selected_year = int(request.GET.get('year', 2026))
    selected_month = int(request.GET.get('month', 0))  # 0 = 전체

    qs = DailySalesTotal.objects.filter(year=selected_year)
    if selected_month:
        qs = qs.filter(month=selected_month)

    totals = qs.aggregate(
        total_gmv=Sum('gmv'),
        total_gsv=Sum('gsv'),
        total_cogs=Sum('cogs'),
        total_expense=Sum('total_expense'),
        total_profit=Sum('operating_profit'),
        total_ad=Sum('performance_ad'),
        total_influencer=Sum('influencer_ad'),
        total_commission=Sum('sales_commission'),
        total_shipping=Sum('shipping'),
        total_tax=Sum('tax'),
        avg_margin=Avg('operating_margin'),
    )

    # B2C 채널별
    b2c_qs = DailySalesB2C.objects.filter(year=selected_year)
    if selected_month:
        b2c_qs = b2c_qs.filter(month=selected_month)
    channel_totals = b2c_qs.aggregate(
        shopify=Sum('shopify'), amazon=Sum('amazon'), tiktok=Sum('tiktok'),
        refund=Sum('refund_total'),
    )

    # 브랜드별
    brand_qs = BrandDailySales.objects.filter(year=selected_year)
    if selected_month:
        brand_qs = brand_qs.filter(month=selected_month)
    brand_totals = brand_qs.values('brand__name_kr').annotate(
        total_gsv=Sum('total_gsv'),
        total_b2c=Sum('b2c_total'),
        total_b2b=Sum('b2b_total'),
    ).order_by('-total_gsv')

    exchange_rate = None
    if selected_month:
        try:
            exchange_rate = ExchangeRate.objects.get(year=selected_year, month=selected_month)
        except ExchangeRate.DoesNotExist:
            pass

    context = {
        'months': months,
        'selected_year': selected_year,
        'selected_month': selected_month,
        'totals': totals,
        'channel_totals': channel_totals,
        'brand_totals': brand_totals,
        'exchange_rate': exchange_rate,
    }
    return render(request, 'sales/dashboard.html', context)


def monthly_pnl(request, year, month):
    """월별 손익관리"""
    daily_data = DailySalesTotal.objects.filter(year=year, month=month).order_by('date')
    b2c_data = DailySalesB2C.objects.filter(year=year, month=month).order_by('date')
    b2b_data = DailySalesB2B.objects.filter(year=year, month=month).order_by('date')

    totals = daily_data.aggregate(
        total_gmv=Sum('gmv'), total_gsv=Sum('gsv'), total_cogs=Sum('cogs'),
        total_expense=Sum('total_expense'), total_profit=Sum('operating_profit'),
        total_ad=Sum('performance_ad'), total_influencer=Sum('influencer_ad'),
        total_commission=Sum('sales_commission'), total_shipping=Sum('shipping'),
    )

    try:
        exchange_rate = ExchangeRate.objects.get(year=year, month=month)
    except ExchangeRate.DoesNotExist:
        exchange_rate = None

    context = {
        'year': year, 'month': month,
        'daily_data': daily_data,
        'b2c_data': b2c_data,
        'b2b_data': b2b_data,
        'totals': totals,
        'exchange_rate': exchange_rate,
        'months': _get_available_months(),
    }
    return render(request, 'sales/monthly_pnl.html', context)


def brand_detail(request, brand_code, year, month):
    """브랜드별 상세"""
    brand = Brand.objects.get(code=brand_code)
    daily = BrandDailySales.objects.filter(brand=brand, year=year, month=month).order_by('date')
    totals = daily.aggregate(
        total_gsv=Sum('total_gsv'), total_b2c=Sum('b2c_total'),
        total_b2b=Sum('b2b_total'), total_refund=Sum('refund_total'),
        total_ad_shopify=Sum('ad_shopify'), total_ad_amazon=Sum('ad_amazon'),
        total_ad_tiktok=Sum('ad_tiktok'),
    )

    context = {
        'brand': brand, 'year': year, 'month': month,
        'daily': daily, 'totals': totals,
        'months': _get_available_months(),
    }
    return render(request, 'sales/brand_detail.html', context)


def channel_analysis(request):
    """채널별 분석"""
    year = int(request.GET.get('year', 2026))
    month = int(request.GET.get('month', 0))

    b2c_qs = DailySalesB2C.objects.filter(year=year)
    if month:
        b2c_qs = b2c_qs.filter(month=month)

    daily = b2c_qs.order_by('date')
    totals = b2c_qs.aggregate(
        shopify=Sum('shopify'), amazon=Sum('amazon'), tiktok=Sum('tiktok'),
        refund=Sum('refund_total'), gsv=Sum('gsv'),
    )

    context = {
        'year': year, 'month': month, 'daily': daily, 'totals': totals,
        'months': _get_available_months(),
    }
    return render(request, 'sales/channel_analysis.html', context)


def shopify_orders(request):
    """쇼피파이 주문 목록"""
    orders = ShopifyOrder.objects.all()
    brand = request.GET.get('brand')
    if brand:
        orders = orders.filter(brand=brand)

    context = {
        'orders': orders[:500],
        'total_count': orders.count(),
        'brands': ShopifyOrder.objects.values_list('brand', flat=True).distinct(),
        'selected_brand': brand,
    }
    return render(request, 'sales/shopify_orders.html', context)


def tiktok_orders(request):
    """틱톡 주문 목록"""
    orders = TiktokOrder.objects.all()
    brand = request.GET.get('brand')
    if brand:
        orders = orders.filter(brand=brand)

    context = {
        'orders': orders[:500],
        'total_count': orders.count(),
        'brands': TiktokOrder.objects.values_list('brand', flat=True).distinct(),
        'selected_brand': brand,
    }
    return render(request, 'sales/tiktok_orders.html', context)


def upload_excel(request):
    """엑셀 파일 업로드"""
    if request.method == 'POST' and request.FILES.get('file'):
        f = request.FILES['file']
        path = f'/tmp/upload_{f.name}'
        with open(path, 'wb+') as dest:
            for chunk in f.chunks():
                dest.write(chunk)
        try:
            call_command('import_excel', path, '--clear')
            messages.success(request, f'"{f.name}" 임포트 완료!')
        except Exception as e:
            messages.error(request, f'임포트 실패: {e}')
        return redirect('sales:dashboard')
    return render(request, 'sales/upload.html')


def api_dashboard_data(request):
    """대시보드 차트 데이터 API"""
    year = int(request.GET.get('year', 2026))

    # 월별 집계
    monthly = DailySalesTotal.objects.filter(year=year).values('month').annotate(
        gsv=Sum('gsv'), cogs=Sum('cogs'), expense=Sum('total_expense'),
        profit=Sum('operating_profit'), ad=Sum('performance_ad'),
    ).order_by('month')

    # 일별 데이터 (선택된 월)
    month = int(request.GET.get('month', 0))
    daily = []
    if month:
        daily_qs = DailySalesTotal.objects.filter(year=year, month=month).order_by('date')
        daily = [
            {'date': str(d.date), 'gsv': d.gsv, 'profit': d.operating_profit,
             'expense': d.total_expense, 'ad': d.performance_ad}
            for d in daily_qs
        ]

    return JsonResponse({
        'monthly': list(monthly),
        'daily': daily,
    }, encoder=DecimalEncoder)


def api_pnl_data(request, year, month):
    """손익 차트 데이터 API"""
    daily = DailySalesTotal.objects.filter(year=year, month=month).order_by('date')
    data = [
        {
            'date': str(d.date),
            'gsv': d.gsv, 'cogs': d.cogs,
            'expense': d.total_expense, 'profit': d.operating_profit,
            'margin': d.operating_margin, 'ad': d.performance_ad,
        }
        for d in daily
    ]
    return JsonResponse({'data': data}, encoder=DecimalEncoder)
