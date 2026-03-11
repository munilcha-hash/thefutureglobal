"""
엑셀 매출/손익 관리 파일을 DB로 임포트하는 관리 커맨드.
3개 지역(US/JP/CN) 엑셀 파일의 서로 다른 시트 구조를 자동 처리.

Usage:
  python manage.py import_excel path/to/미국.xlsx --region us
  python manage.py import_excel path/to/일본.xlsx --region jp
  python manage.py import_excel path/to/중화권.xlsx --region cn
"""
import pandas as pd
from decimal import Decimal, InvalidOperation
from datetime import datetime
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from sales.models import (
    ExchangeRate, Brand, DailySalesTotal, DailySalesB2B,
    DailySalesB2C, BrandDailySales, TaxByState
)
from sales.region_config import get_region_config


def sd(val, default=0):
    """safe_decimal"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return Decimal(str(default)) if default is not None else None
    s = str(val).strip()
    if not s or s in ('', '-', '#DIV/0!', '#NUM!', '#REF!', '#VALUE!', '#N/A'):
        return Decimal(str(default)) if default is not None else None
    try:
        return Decimal(s.replace(',', ''))
    except (InvalidOperation, ValueError):
        return Decimal(str(default)) if default is not None else None


def sdate(val):
    """safe_date"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()
    if not s or '합계' in s:
        return None
    for fmt in ('%Y-%m-%d', '%Y-%m-%d %H:%M:%S', '%m/%d/%Y'):
        try:
            return datetime.strptime(s.split('+')[0].strip(), fmt).date()
        except ValueError:
            continue
    return None


class Command(BaseCommand):
    help = '엑셀 매출/손익 관리 파일을 DB로 임포트'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str)
        parser.add_argument('--region', type=str, default='us',
                            choices=['us', 'cn', 'jp'])
        parser.add_argument('--clear', action='store_true',
                            help='해당 지역 기존 데이터 삭제 후 임포트')

    def handle(self, *args, **options):
        file_path = options['file_path']
        self.region = options['region']
        self.config = get_region_config(self.region)

        xls = pd.ExcelFile(file_path)
        self.stdout.write(f"[{self.region}] 시트: {xls.sheet_names}")

        if options['clear']:
            self._clear_data()

        self._init_brands()

        # 1) 손익관리 시트 임포트
        for sheet in xls.sheet_names:
            if sheet.startswith('손익관리_'):
                month_str = sheet.replace('손익관리_', '')
                self._import_pnl(xls, sheet, month_str)

        # 2) 브랜드 매출 시트 임포트
        brand_keywords = self.config.get('brand_keywords', [])
        for sheet in xls.sheet_names:
            if '매출_' in sheet and not any(x in sheet for x in ['RAW', '경모']):
                for kw in brand_keywords:
                    if kw in sheet:
                        self._import_brand(xls, sheet)
                        break

        # 3) 브랜드 데이터로 B2C 집계
        self._compute_b2c()

        # 4) Tax (US only)
        if self.region == 'us' and 'Tax_TT' in xls.sheet_names:
            self._import_tax(xls, 'Tax_TT')

        self.stdout.write(self.style.SUCCESS(f"[{self.region}] 임포트 완료!"))

    def _clear_data(self):
        for model in [DailySalesTotal, DailySalesB2B, DailySalesB2C,
                      BrandDailySales, TaxByState]:
            n = model.objects.filter(region=self.region).delete()[0]
            if n:
                self.stdout.write(f"  {model.__name__}: {n}건 삭제")

    def _init_brands(self):
        for code, name, name_kr in self.config.get('brands', []):
            Brand.objects.get_or_create(
                code=code, region=self.region,
                defaults={'name': name, 'name_kr': name_kr}
            )

    # ─── PNL (손익관리) ─────────────────────────────────

    @transaction.atomic
    def _import_pnl(self, xls, sheet_name, month_str):
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  {sheet_name} 임포트 중...")

        month_num = self._parse_month(month_str)
        rate_val = sd(df.iloc[1, 2], 1)
        ExchangeRate.objects.update_or_create(
            year=2026, month=month_num, region=self.region,
            defaults={'rate': rate_val}
        )

        # 헤더 Row 4 분석해서 컬럼 매핑 자동 감지
        header_row = [str(df.iloc[4, c]) if pd.notna(df.iloc[4, c]) else ''
                      for c in range(min(25, len(df.columns)))]
        col_map = self._detect_pnl_columns(header_row)
        b2b_start = self._detect_b2b_start(header_row)

        count = 0
        for i in range(5, len(df)):
            date_val = sdate(df.iloc[i, 1])
            if date_val is None:
                continue

            row = df.iloc[i]

            DailySalesTotal.objects.update_or_create(
                date=date_val, region=self.region,
                defaults={
                    'year': date_val.year, 'month': date_val.month,
                    'gmv': sd(row[col_map['gmv']]),
                    'gsv': sd(row[col_map['gsv']]),
                    'cogs': sd(row[col_map['cogs']]),
                    'total_expense': sd(row[col_map['expense']]),
                    'performance_ad': sd(row[col_map['perf_ad']]),
                    'influencer_ad': sd(row[col_map['influencer']]),
                    'sales_commission': sd(row[col_map['commission']]),
                    'shipping': sd(row[col_map['shipping']]),
                    'tax': sd(row[col_map['tax']]),
                    'operating_profit': sd(row[col_map['op_profit']]),
                    'operating_margin': sd(row[col_map['op_margin']], None),
                }
            )

            # B2B
            if b2b_start:
                DailySalesB2B.objects.update_or_create(
                    date=date_val, region=self.region,
                    defaults={
                        'year': date_val.year, 'month': date_val.month,
                        'sales_total': sd(row[b2b_start]),
                        'sales_us': sd(row[b2b_start + 1]),
                        'cogs': sd(row[b2b_start + 2]) if b2b_start + 2 < len(row) else Decimal('0'),
                        'total_expense': sd(row[b2b_start + 3]) if b2b_start + 3 < len(row) else Decimal('0'),
                        'shipping': sd(row[b2b_start + 4]) if b2b_start + 4 < len(row) else Decimal('0'),
                    }
                )
            count += 1

        self.stdout.write(f"    → {count}일 데이터")

    def _detect_pnl_columns(self, header):
        """Row 4 헤더에서 컬럼 인덱스 자동 감지"""
        m = {'gmv': 2, 'gsv': 3, 'cogs': 4, 'expense': 5,
             'perf_ad': 6, 'influencer': 7, 'commission': 8,
             'shipping': 9, 'tax': 10, 'op_profit': 11, 'op_margin': 12}

        # 일본은 '인앱 광고비' 컬럼이 추가되어 8번부터 한 칸씩 밀림
        if any('인앱' in h for h in header):
            m['commission'] = 9
            m['shipping'] = 10
            m['tax'] = 11
            m['op_profit'] = 12
            m['op_margin'] = 13
        return m

    def _detect_b2b_start(self, header):
        """B2B 섹션 시작 컬럼 찾기"""
        for i, h in enumerate(header):
            if 'B2B' in h and '합계' in h:
                return i
        return None

    # ─── 브랜드 매출 ─────────────────────────────────

    @transaction.atomic
    def _import_brand(self, xls, sheet_name):
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  {sheet_name} 임포트 중...")

        brand_map = self.config.get('brand_map', {})
        num_cols = len(df.columns)

        # Row 2 서브헤더로 채널 구조 감지
        sub_header = [str(df.iloc[2, c]) if c < num_cols and pd.notna(df.iloc[2, c]) else ''
                      for c in range(min(50, num_cols))]

        count = 0
        for i in range(3, len(df)):
            date_val = sdate(df.iloc[i, 1])
            if date_val is None:
                continue

            row = df.iloc[i]
            brand_name = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''
            brand_code = brand_map.get(brand_name)
            if not brand_code:
                continue

            try:
                brand = Brand.objects.get(code=brand_code, region=self.region)
            except Brand.DoesNotExist:
                continue

            defaults = self._parse_brand_row(row, sub_header, num_cols)
            defaults['year'] = date_val.year
            defaults['month'] = date_val.month

            BrandDailySales.objects.update_or_create(
                date=date_val, brand=brand, region=self.region,
                defaults=defaults
            )
            count += 1

        self.stdout.write(f"    → {count}일 데이터")

    def _parse_brand_row(self, row, sub_header, num_cols):
        """지역별로 다른 브랜드 시트 구조를 파싱"""
        d = {}

        def g(idx):
            """safe get by position"""
            return sd(row.iloc[idx]) if idx < num_cols else Decimal('0')

        if self.region == 'us':
            # US: 쇼피파이(3) 아마존(4) 틱톡샵(5) B2C합계(6) 환불_쇼피(7) 환불_아마존(8) 환불_틱톡(9) 환불합계(10)
            #     GSV_쇼피(11) GSV_아마존(12) GSV_틱톡(13) GSV합계(14) B2B_미국(15) B2B합계(16) 전체GSV(17) _(18) 쇼피광고(19)
            d['b2c_shopify'] = g(3)
            d['b2c_amazon'] = g(4)
            d['b2c_tiktok'] = g(5)
            d['b2c_total'] = g(6)
            d['refund_shopify'] = g(7)
            d['refund_amazon'] = g(8)
            d['refund_tiktok'] = g(9)
            d['refund_total'] = g(10)
            d['gsv'] = g(14)
            d['b2b_us'] = g(15)
            d['b2b_total'] = g(16)
            d['total_gsv'] = g(17)
            d['ad_shopify'] = g(19)
            d['ad_amazon'] = g(20)
            d['ad_tiktok'] = g(21)

        elif self.region == 'jp':
            # JP: 큐텐(3) B2C합계(4) 환불_큐텐(5) 환불합계(6) GSV_큐텐(7) GSV합계(8) B2B(9) B2B합계(10) 전체GSV(11) _(12) 큐텐광고(13)
            d['b2c_qoo10'] = g(3)
            d['b2c_total'] = g(4)
            d['refund_qoo10'] = g(5)
            d['refund_total'] = g(6)
            d['gsv'] = g(8)
            d['b2b_us'] = g(9)
            d['b2b_total'] = g(10)
            d['total_gsv'] = g(11)
            d['ad_qoo10'] = g(13)

        elif self.region == 'cn':
            # 컬럼 수로 브랜드 타입 감지
            has_shopee = any('쇼피' in h or '싱가폴' in h for h in sub_header)

            if num_cols <= 15:
                # 테트라큐어: 도우인(3) 환불(4) GSV(5) — 11컬럼
                d['b2c_total'] = g(3)
                d['refund_total'] = g(4)
                d['gsv'] = g(5)
                d['total_gsv'] = g(5)
            elif has_shopee:
                # 닥터블릿 (쇼피싱가폴 포함, 49컬럼)
                # B2C: 도우인(3) 티몰(4) 콰이쇼우(5) 타오펀샤오(6) 핀둬둬(7) 쇼피싱가폴(8) B2C합계(9)
                # 환불: 도우인(10)~쇼피(15) 합계(16)
                # GSV: 도우인(17)~쇼피(22) 합계(23)
                # B2B: 중국(24)
                d['b2c_total'] = g(9)
                d['b2c_shopee'] = g(8)
                d['refund_total'] = g(16)
                d['gsv'] = g(23)
                d['total_gsv'] = g(23)
                d['b2b_us'] = g(24)
                # B2B합계 = B2B 전체
                b2b_sum = Decimal('0')
                for c in range(24, min(num_cols, 30)):
                    h = sub_header[c] if c < len(sub_header) else ''
                    if 'GSV' in h or '전체' in h:
                        break
                    b2b_sum += g(c)
                d['b2b_total'] = b2b_sum
            else:
                # EOA, 낫띵베럴 (5채널, 45컬럼)
                # B2C: 도우인(3) 티몰(4) 콰이쇼우(5) 타오펀샤오(6) 핀둬둬(7) B2C합계(8)
                # 환불: 도우인(9) 티몰(10) 콰이쇼우(11) 타오펀샤오(12) 핀둬둬(13) 합계(14)
                # GSV: 도우인(15) 티몰(16) 콰이쇼우(17) 타오펀샤오(18) 핀둬둬(19) 합계(20)
                # B2B: 중국(21) 대만(22) 홍콩(23) 싱가폴(24)
                d['b2c_total'] = g(8)
                d['refund_total'] = g(14)
                d['gsv'] = g(20)
                d['total_gsv'] = g(20)
                d['b2b_us'] = g(21)
                b2b_sum = Decimal('0')
                for c in range(21, min(num_cols, 26)):
                    h = sub_header[c] if c < len(sub_header) else ''
                    if 'GSV' in h or '전체' in h or '합계' in h:
                        break
                    b2b_sum += g(c)
                d['b2b_total'] = b2b_sum

            d.setdefault('b2b_total', Decimal('0'))
            d.setdefault('b2b_us', Decimal('0'))

        # 기본값 채우기
        for f in ['b2c_shopify', 'b2c_amazon', 'b2c_tiktok', 'b2c_shopee', 'b2c_qoo10',
                   'b2c_total', 'refund_shopify', 'refund_amazon', 'refund_tiktok',
                   'refund_shopee', 'refund_qoo10', 'refund_total', 'gsv',
                   'b2b_us', 'b2b_total', 'total_gsv',
                   'ad_shopify', 'ad_amazon', 'ad_tiktok', 'ad_shopee', 'ad_qoo10']:
            d.setdefault(f, Decimal('0'))

        return d

    # ─── B2C 집계 (브랜드 → B2C) ───────────────────────

    @transaction.atomic
    def _compute_b2c(self):
        """BrandDailySales에서 DailySalesB2C 집계"""
        from django.db.models import Sum

        dates = BrandDailySales.objects.filter(
            region=self.region
        ).values('date', 'year', 'month').distinct()

        count = 0
        for d in dates:
            date_val = d['date']
            brands = BrandDailySales.objects.filter(
                date=date_val, region=self.region
            )

            agg = brands.aggregate(
                shopify=Sum('b2c_shopify'), amazon=Sum('b2c_amazon'),
                tiktok=Sum('b2c_tiktok'), shopee=Sum('b2c_shopee'),
                qoo10=Sum('b2c_qoo10'), b2c_total=Sum('b2c_total'),
                r_shopify=Sum('refund_shopify'), r_amazon=Sum('refund_amazon'),
                r_tiktok=Sum('refund_tiktok'), r_shopee=Sum('refund_shopee'),
                r_qoo10=Sum('refund_qoo10'), r_total=Sum('refund_total'),
                gsv=Sum('gsv'), total_gsv=Sum('total_gsv'),
            )

            DailySalesB2C.objects.update_or_create(
                date=date_val, region=self.region,
                defaults={
                    'year': d['year'], 'month': d['month'],
                    'shopify': agg['shopify'] or 0,
                    'amazon': agg['amazon'] or 0,
                    'tiktok': agg['tiktok'] or 0,
                    'shopee': agg['shopee'] or 0,
                    'qoo10': agg['qoo10'] or 0,
                    'b2c_total': agg['b2c_total'] or 0,
                    'refund_shopify': agg['r_shopify'] or 0,
                    'refund_amazon': agg['r_amazon'] or 0,
                    'refund_tiktok': agg['r_tiktok'] or 0,
                    'refund_shopee': agg['r_shopee'] or 0,
                    'refund_qoo10': agg['r_qoo10'] or 0,
                    'refund_total': agg['r_total'] or 0,
                    'gsv': agg['gsv'] or 0,
                }
            )
            count += 1

        self.stdout.write(f"  B2C 집계: {count}일")

    # ─── Tax ──────────────────────────────────────────

    @transaction.atomic
    def _import_tax(self, xls, sheet_name):
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  {sheet_name} 임포트 중...")

        dates = []
        for col in range(2, min(20, len(df.columns))):
            d = sdate(df.iloc[2, col])
            if d:
                dates.append((col, d))

        count = 0
        for i in range(3, len(df)):
            state = str(df.iloc[i, 1]).strip() if pd.notna(df.iloc[i, 1]) else ''
            if not state:
                continue
            for col, d in dates:
                amt = sd(df.iloc[i, col])
                if amt and amt != 0:
                    TaxByState.objects.update_or_create(
                        state_code=state, year=d.year, month=d.month,
                        region=self.region,
                        defaults={'amount': amt}
                    )
                    count += 1
        self.stdout.write(f"    → {count}건")

    def _parse_month(self, s):
        m = {'1월': 1, '2월': 2, '3월': 3, '4월': 4, '5월': 5, '6월': 6,
             '7월': 7, '8월': 8, '9월': 9, '10월': 10, '11월': 11, '12월': 12}
        return m.get(s, 1)
