import json
import os
from io import StringIO
from decimal import Decimal
from django.shortcuts import render, redirect, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Sum, Avg, Max
from django.core.management import call_command
from .models import (
    ExchangeRate, Brand, DailySalesTotal, DailySalesB2B,
    DailySalesB2C, BrandDailySales, ShopifyOrder, TiktokOrder,
    ShopeeOrder, Qoo10Order, TaxByState
)
from .region_config import REGION_CONFIG, get_region_config
from .utils import save_upload, detect_platform


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _get_current_region(request):
    return request.session.get('current_region', 'us')


def _get_available_months(region):
    months = DailySalesTotal.objects.filter(region=region).values('year', 'month').distinct().order_by('year', 'month')
    return list(months)


def set_region(request, region):
    """지역 전환"""
    if region in REGION_CONFIG:
        request.session['current_region'] = region
    return redirect('sales:dashboard')


def dashboard(request):
    """메인 대시보드"""
    region = _get_current_region(request)
    config = get_region_config(region)
    months = _get_available_months(region)
    selected_year = int(request.GET.get('year', 2026))
    selected_month = int(request.GET.get('month', 0))

    qs = DailySalesTotal.objects.filter(year=selected_year, region=region)
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

    # B2C 채널별 - 동적 집계
    b2c_qs = DailySalesB2C.objects.filter(year=selected_year, region=region)
    if selected_month:
        b2c_qs = b2c_qs.filter(month=selected_month)

    channel_fields = config.get('channel_fields', [])
    channel_agg = {}
    for field in channel_fields:
        channel_agg[field] = Sum(field)
    channel_agg['refund'] = Sum('refund_total')
    channel_totals = b2c_qs.aggregate(**channel_agg)

    # 브랜드별
    brand_qs = BrandDailySales.objects.filter(year=selected_year, region=region)
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
            exchange_rate = ExchangeRate.objects.get(year=selected_year, month=selected_month, region=region)
        except ExchangeRate.DoesNotExist:
            pass

    channels = config.get('channels', {})

    # 채널 데이터를 템플릿 친화적 리스트로 변환
    channel_list = []
    for field in channel_fields:
        label = channels.get(field, field)
        value = channel_totals.get(field) or 0
        channel_list.append({'field': field, 'label': label, 'value': value})
    refund_total = channel_totals.get('refund') or 0

    context = {
        'months': months,
        'selected_year': selected_year,
        'selected_month': selected_month,
        'totals': totals,
        'channel_list': channel_list,
        'refund_total': refund_total,
        'brand_totals': brand_totals,
        'exchange_rate': exchange_rate,
        'channels': channels,
        'channel_fields': channel_fields,
    }
    return render(request, 'sales/dashboard.html', context)


def monthly_pnl(request, year, month):
    """월별 손익관리"""
    region = _get_current_region(request)
    daily_data = DailySalesTotal.objects.filter(year=year, month=month, region=region).order_by('date')
    b2c_data = DailySalesB2C.objects.filter(year=year, month=month, region=region).order_by('date')
    b2b_data = DailySalesB2B.objects.filter(year=year, month=month, region=region).order_by('date')

    totals = daily_data.aggregate(
        total_gmv=Sum('gmv'), total_gsv=Sum('gsv'), total_cogs=Sum('cogs'),
        total_expense=Sum('total_expense'), total_profit=Sum('operating_profit'),
        total_ad=Sum('performance_ad'), total_influencer=Sum('influencer_ad'),
        total_commission=Sum('sales_commission'), total_shipping=Sum('shipping'),
    )

    try:
        exchange_rate = ExchangeRate.objects.get(year=year, month=month, region=region)
    except ExchangeRate.DoesNotExist:
        exchange_rate = None

    context = {
        'year': year, 'month': month,
        'daily_data': daily_data,
        'b2c_data': b2c_data,
        'b2b_data': b2b_data,
        'totals': totals,
        'exchange_rate': exchange_rate,
        'months': _get_available_months(region),
    }
    return render(request, 'sales/monthly_pnl.html', context)


def brand_detail(request, brand_code, year, month):
    """브랜드별 상세"""
    region = _get_current_region(request)
    config = get_region_config(region)
    channels = config.get('channels', {})

    # Brand가 DB에 없으면 config에서 이름 가져와서 임시 객체 생성
    try:
        brand = Brand.objects.get(code=brand_code, region=region)
    except Brand.DoesNotExist:
        # region_config에서 브랜드 정보 찾기
        brand_info = None
        for code, name, name_kr in config.get('brands', []):
            if code == brand_code:
                brand_info = (code, name, name_kr)
                break
        if not brand_info:
            from django.http import Http404
            raise Http404
        # DB에 없으면 생성
        brand = Brand.objects.create(
            code=brand_info[0], region=region,
            name=brand_info[1], name_kr=brand_info[2]
        )

    daily = BrandDailySales.objects.filter(brand=brand, year=year, month=month, region=region).order_by('date')
    totals = daily.aggregate(
        total_gsv=Sum('total_gsv'), total_b2c=Sum('b2c_total'),
        total_b2b=Sum('b2b_total'), total_refund=Sum('refund_total'),
    )

    context = {
        'brand': brand, 'year': year, 'month': month,
        'daily': daily, 'totals': totals,
        'months': _get_available_months(region),
        'channels': channels,
    }
    return render(request, 'sales/brand_detail.html', context)


def channel_analysis(request):
    """채널별 분석"""
    region = _get_current_region(request)
    config = get_region_config(region)
    year = int(request.GET.get('year', 2026))
    month = int(request.GET.get('month', 0))

    b2c_qs = DailySalesB2C.objects.filter(year=year, region=region)
    if month:
        b2c_qs = b2c_qs.filter(month=month)

    daily = b2c_qs.order_by('date')

    channel_fields = config.get('channel_fields', [])
    channel_agg = {}
    for field in channel_fields:
        channel_agg[field] = Sum(field)
    channel_agg['refund'] = Sum('refund_total')
    channel_agg['gsv'] = Sum('gsv')
    totals = b2c_qs.aggregate(**channel_agg)

    channels = config.get('channels', {})

    # 채널 데이터를 템플릿 친화적 리스트로 변환
    channel_list = []
    for field in channel_fields:
        label = channels.get(field, field)
        value = totals.get(field) or 0
        channel_list.append({'field': field, 'label': label, 'value': value})

    context = {
        'year': year, 'month': month,
        'daily': daily, 'totals': totals,
        'months': _get_available_months(region),
        'channels': channels,
        'channel_fields': channel_fields,
        'channel_list': channel_list,
    }
    return render(request, 'sales/channel_analysis.html', context)


def shopify_orders(request):
    """쇼피파이 주문 목록"""
    orders = ShopifyOrder.objects.filter(region='us')
    brand = request.GET.get('brand')
    if brand:
        orders = orders.filter(brand=brand)

    context = {
        'orders': orders[:500],
        'total_count': orders.count(),
        'brands': ShopifyOrder.objects.filter(region='us').values_list('brand', flat=True).distinct(),
        'selected_brand': brand,
    }
    return render(request, 'sales/shopify_orders.html', context)


def tiktok_orders(request):
    """틱톡 주문 목록"""
    orders = TiktokOrder.objects.filter(region='us')
    brand = request.GET.get('brand')
    if brand:
        orders = orders.filter(brand=brand)

    context = {
        'orders': orders[:500],
        'total_count': orders.count(),
        'brands': TiktokOrder.objects.filter(region='us').values_list('brand', flat=True).distinct(),
        'selected_brand': brand,
    }
    return render(request, 'sales/tiktok_orders.html', context)


def shopee_orders(request):
    """쇼피 주문 목록 (China)"""
    orders = ShopeeOrder.objects.filter(region='cn')
    brand = request.GET.get('brand')
    if brand:
        orders = orders.filter(brand=brand)

    context = {
        'orders': orders[:500],
        'total_count': orders.count(),
        'brands': ShopeeOrder.objects.filter(region='cn').values_list('brand', flat=True).distinct(),
        'selected_brand': brand,
    }
    return render(request, 'sales/shopee_orders.html', context)


def qoo10_orders(request):
    """큐텐 주문 목록 (Japan)"""
    orders = Qoo10Order.objects.filter(region='jp')
    brand = request.GET.get('brand')
    if brand:
        orders = orders.filter(brand=brand)

    context = {
        'orders': orders[:500],
        'total_count': orders.count(),
        'brands': Qoo10Order.objects.filter(region='jp').values_list('brand', flat=True).distinct(),
        'selected_brand': brand,
    }
    return render(request, 'sales/qoo10_orders.html', context)


def upload_raw(request):
    """플랫폼별 RAW 파일 업로드 페이지 (GET만)"""
    context = {
        'shopify_count': ShopifyOrder.objects.count(),
        'shopify_latest': ShopifyOrder.objects.aggregate(d=Max('order_date'))['d'],
        'tiktok_count': TiktokOrder.objects.count(),
        'tiktok_latest': TiktokOrder.objects.aggregate(d=Max('order_date'))['d'],
        'shopee_count': ShopeeOrder.objects.count(),
        'shopee_latest': ShopeeOrder.objects.aggregate(d=Max('order_date'))['d'],
        'qoo10_count': Qoo10Order.objects.count(),
        'qoo10_latest': Qoo10Order.objects.aggregate(d=Max('order_date'))['d'],
    }
    return render(request, 'sales/upload_raw.html', context)


@csrf_exempt
def api_upload_raw(request):
    """AJAX RAW 파일 업로드 API (JSON 응답)"""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST만 허용'}, status=405)

    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'ok': False, 'error': '파일이 없습니다'})

    original_name = f.name

    # 파일 사이즈 제한 (10MB)
    if f.size > 10 * 1024 * 1024:
        return JsonResponse({'ok': False, 'error': f'파일이 너무 큽니다 ({f.size // 1024 // 1024}MB). 최대 10MB'})

    platform = request.POST.get('platform', '')
    clear_date = request.POST.get('clear_date') == 'on'

    path = save_upload(f)

    try:
        if not platform:
            platform = detect_platform(original_name) or ''

        cmd_args = [path, '--original-filename', original_name]
        if platform:
            cmd_args += ['--platform', platform]
        if clear_date:
            cmd_args.append('--clear-date')

        out = StringIO()
        err = StringIO()
        call_command('import_raw', *cmd_args, stdout=out, stderr=err)

        output = out.getvalue().strip()
        last_line = output.split('\n')[-1] if output else '완료'
        error_output = err.getvalue().strip()

        result = {
            'ok': True,
            'message': last_line,
            'platform': platform,
            'filename': original_name,
            'warning': error_output[:200] if error_output else None,
        }

        # 현황 데이터도 같이 반환
        result['counts'] = {
            'shopify': ShopifyOrder.objects.count(),
            'tiktok': TiktokOrder.objects.count(),
            'shopee': ShopeeOrder.objects.count(),
            'qoo10': Qoo10Order.objects.count(),
        }
        return JsonResponse(result)

    except Exception as e:
        return JsonResponse({
            'ok': False,
            'error': str(e)[:300],
            'platform': platform,
            'filename': original_name,
        })
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


@csrf_exempt
def api_upload_excel(request):
    """AJAX PNL 엑셀 업로드 API (JSON 응답)"""
    if request.method != 'POST':
        return JsonResponse({'ok': False, 'error': 'POST만 허용'}, status=405)

    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'ok': False, 'error': '파일이 없습니다'})

    region = request.POST.get('region', '')
    if region not in ('us', 'cn', 'jp'):
        return JsonResponse({'ok': False, 'error': '지역을 선택해주세요 (us/cn/jp)'})

    if f.size > 30 * 1024 * 1024:
        return JsonResponse({'ok': False, 'error': f'파일이 너무 큽니다 ({f.size // 1024 // 1024}MB). 최대 30MB'})

    path = save_upload(f)

    try:
        out = StringIO()
        err = StringIO()
        call_command('import_excel', path, '--region', region, '--clear',
                     stdout=out, stderr=err)

        output = out.getvalue().strip()
        last_line = output.split('\n')[-1] if output else '완료'
        error_output = err.getvalue().strip()

        return JsonResponse({
            'ok': True,
            'message': last_line,
            'region': region,
            'filename': f.name,
            'detail': output[-500:] if output else '',
            'warning': error_output[:200] if error_output else None,
        })

    except Exception as e:
        return JsonResponse({
            'ok': False,
            'error': str(e)[:300],
            'region': region,
            'filename': f.name,
        })
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def api_dashboard_data(request):
    """대시보드 차트 데이터 API"""
    region = _get_current_region(request)
    year = int(request.GET.get('year', 2026))

    monthly = DailySalesTotal.objects.filter(year=year, region=region).values('month').annotate(
        gsv=Sum('gsv'), cogs=Sum('cogs'), expense=Sum('total_expense'),
        profit=Sum('operating_profit'), ad=Sum('performance_ad'),
    ).order_by('month')

    month = int(request.GET.get('month', 0))
    daily = []
    if month:
        daily_qs = DailySalesTotal.objects.filter(year=year, month=month, region=region).order_by('date')
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
    region = _get_current_region(request)
    daily = DailySalesTotal.objects.filter(year=year, month=month, region=region).order_by('date')
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
