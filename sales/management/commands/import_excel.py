"""
엑셀 파일에서 데이터를 PostgreSQL로 임포트하는 관리 커맨드.
Usage: python manage.py import_excel path/to/file.xlsx
"""
import pandas as pd
from decimal import Decimal, InvalidOperation
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from sales.models import (
    ExchangeRate, Brand, DailySalesTotal, DailySalesB2B,
    DailySalesB2C, BrandDailySales, ShopifyOrder, TiktokOrder, TaxByState
)


def safe_decimal(val, default=0):
    if pd.isna(val) or val is None or val == '' or val == '#DIV/0!':
        return Decimal(str(default))
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return Decimal(str(default))


def safe_date(val):
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%Y-%m-%d %H:%M:%S'):
            try:
                return datetime.strptime(val.split('+')[0].strip(), fmt).date()
            except ValueError:
                continue
    return None


def safe_str(val, default=''):
    if pd.isna(val) or val is None:
        return default
    return str(val).strip()


def safe_int(val, default=0):
    if pd.isna(val) or val is None:
        return default
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return default


class Command(BaseCommand):
    help = '엑셀 매출/손익 관리 파일을 DB로 임포트'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='엑셀 파일 경로')
        parser.add_argument('--clear', action='store_true', help='기존 데이터 삭제 후 임포트')

    def handle(self, *args, **options):
        file_path = options['file_path']
        xls = pd.ExcelFile(file_path)
        self.stdout.write(f"시트 목록: {xls.sheet_names}")

        if options['clear']:
            self.stdout.write("기존 데이터 삭제 중...")
            for model in [DailySalesTotal, DailySalesB2B, DailySalesB2C,
                          BrandDailySales, ShopifyOrder, TiktokOrder, TaxByState]:
                model.objects.all().delete()

        self._init_brands()

        # 월별 손익관리 시트 임포트
        for sheet in xls.sheet_names:
            if sheet.startswith('손익관리_'):
                month_str = sheet.replace('손익관리_', '')
                self._import_pnl(xls, sheet, month_str)

        # 브랜드별 매출 시트
        for sheet in xls.sheet_names:
            if '매출_' in sheet and ('닥터블릿' in sheet or 'Calo' in sheet):
                self._import_brand_sales(xls, sheet)

        # RAW 데이터
        if '쇼피파이 매출_RAW' in xls.sheet_names:
            self._import_shopify_raw(xls)
        if '틱톡샵 매출_RAW' in xls.sheet_names:
            self._import_tiktok_raw(xls)
        if 'Tax_TT' in xls.sheet_names:
            self._import_tax(xls)

        self.stdout.write(self.style.SUCCESS("임포트 완료!"))

    def _init_brands(self):
        brands = [
            ('doctorblet', 'Dr.Blet', '닥터블릿'),
            ('pooeng', 'Pooeng', '푸응'),
            ('delinoshi', 'Delinoshi', '딜리노쉬'),
            ('calo', 'Calo', 'Calo'),
        ]
        for code, name, name_kr in brands:
            Brand.objects.get_or_create(code=code, defaults={'name': name, 'name_kr': name_kr})

    @transaction.atomic
    def _import_pnl(self, xls, sheet_name, month_str):
        """손익관리 시트 임포트"""
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  {sheet_name} 임포트 중...")

        # 환율 추출 (row 1, col 2)
        rate_val = safe_decimal(df.iloc[1, 2], 1446)
        month_num = self._parse_month(month_str)

        ExchangeRate.objects.update_or_create(
            year=2026, month=month_num,
            defaults={'rate': rate_val}
        )

        # 데이터 rows (row 5 ~ row before 합계)
        for i in range(5, len(df)):
            row = df.iloc[i]
            date_val = safe_date(row[1])
            if date_val is None:
                continue
            if '합계' in str(row[1]):
                break

            # 전체 손익 (cols 1~12)
            DailySalesTotal.objects.update_or_create(
                date=date_val,
                defaults={
                    'year': date_val.year, 'month': date_val.month,
                    'gmv': safe_decimal(row[2]),
                    'gsv': safe_decimal(row[3]),
                    'cogs': safe_decimal(row[4]),
                    'total_expense': safe_decimal(row[5]),
                    'performance_ad': safe_decimal(row[6]),
                    'influencer_ad': safe_decimal(row[7]),
                    'sales_commission': safe_decimal(row[8]),
                    'shipping': safe_decimal(row[9]),
                    'tax': safe_decimal(row[10]),
                    'operating_profit': safe_decimal(row[11]),
                    'operating_margin': safe_decimal(row[12], None),
                }
            )

            # B2B (cols 14~22)
            DailySalesB2B.objects.update_or_create(
                date=date_val,
                defaults={
                    'year': date_val.year, 'month': date_val.month,
                    'sales_total': safe_decimal(row[15]),
                    'sales_us': safe_decimal(row[16]),
                    'cogs': safe_decimal(row[17]),
                    'total_expense': safe_decimal(row[18]),
                    'shipping': safe_decimal(row[19]),
                    'tax': safe_decimal(row[20]),
                    'operating_profit': safe_decimal(row[21]),
                }
            )

            # B2C (cols 24~42)
            DailySalesB2C.objects.update_or_create(
                date=date_val,
                defaults={
                    'year': date_val.year, 'month': date_val.month,
                    'b2c_total': safe_decimal(row[25]),
                    'shopify': safe_decimal(row[26]),
                    'amazon': safe_decimal(row[27]),
                    'tiktok': safe_decimal(row[28]),
                    'refund_shopify': safe_decimal(row[29]),
                    'refund_amazon': safe_decimal(row[30]),
                    'refund_tiktok': safe_decimal(row[31]),
                    'refund_total': safe_decimal(row[32]) if len(row) > 32 else Decimal('0'),
                    'gsv': safe_decimal(row[33]) if len(row) > 33 else Decimal('0'),
                    'cogs': safe_decimal(row[34]) if len(row) > 34 else Decimal('0'),
                    'total_expense': safe_decimal(row[35]) if len(row) > 35 else Decimal('0'),
                    'performance_ad': safe_decimal(row[36]) if len(row) > 36 else Decimal('0'),
                    'influencer_ad': safe_decimal(row[37]) if len(row) > 37 else Decimal('0'),
                    'sales_commission': safe_decimal(row[38]) if len(row) > 38 else Decimal('0'),
                    'shipping': safe_decimal(row[39]) if len(row) > 39 else Decimal('0'),
                    'tax': safe_decimal(row[40]) if len(row) > 40 else Decimal('0'),
                    'operating_profit': safe_decimal(row[41]) if len(row) > 41 else Decimal('0'),
                    'operating_margin': safe_decimal(row[42], None) if len(row) > 42 else None,
                }
            )

        count = DailySalesTotal.objects.filter(month=month_num).count()
        self.stdout.write(f"    → {count}일 데이터 임포트 완료")

    @transaction.atomic
    def _import_brand_sales(self, xls, sheet_name):
        """브랜드 매출 시트 임포트"""
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  {sheet_name} 임포트 중...")

        # 브랜드 매핑
        brand_map = {
            '닥터블릿': 'doctorblet', '푸응': 'pooeng', '딜리노쉬': 'delinoshi', 'Calo': 'calo',
        }

        for i in range(3, len(df)):
            row = df.iloc[i]
            date_val = safe_date(row[1])
            if date_val is None:
                continue
            if '합계' in str(row[1]):
                break

            brand_name = safe_str(row[2])
            brand_code = brand_map.get(brand_name)
            if not brand_code:
                continue

            try:
                brand = Brand.objects.get(code=brand_code)
            except Brand.DoesNotExist:
                continue

            BrandDailySales.objects.update_or_create(
                date=date_val, brand=brand,
                defaults={
                    'year': date_val.year, 'month': date_val.month,
                    'b2c_shopify': safe_decimal(row[3]),
                    'b2c_amazon': safe_decimal(row[4]) if len(row) > 4 else Decimal('0'),
                    'b2c_tiktok': safe_decimal(row[5]) if len(row) > 5 else Decimal('0'),
                    'b2c_total': safe_decimal(row[6]) if len(row) > 6 else Decimal('0'),
                    'refund_shopify': safe_decimal(row[7]) if len(row) > 7 else Decimal('0'),
                    'refund_amazon': safe_decimal(row[8]) if len(row) > 8 else Decimal('0'),
                    'refund_tiktok': safe_decimal(row[9]) if len(row) > 9 else Decimal('0'),
                    'refund_total': safe_decimal(row[10]) if len(row) > 10 else Decimal('0'),
                    'gsv': safe_decimal(row[11]) if len(row) > 11 else Decimal('0'),
                    'b2b_us': safe_decimal(row[15]) if len(row) > 15 else Decimal('0'),
                    'b2b_total': safe_decimal(row[16]) if len(row) > 16 else Decimal('0'),
                    'total_gsv': safe_decimal(row[17]) if len(row) > 17 else Decimal('0'),
                    'ad_shopify': safe_decimal(row[19]) if len(row) > 19 else Decimal('0'),
                    'ad_amazon': safe_decimal(row[20]) if len(row) > 20 else Decimal('0'),
                    'ad_tiktok': safe_decimal(row[21]) if len(row) > 21 else Decimal('0'),
                }
            )

    @transaction.atomic
    def _import_shopify_raw(self, xls):
        """쇼피파이 RAW 데이터 임포트"""
        df = pd.read_excel(xls, sheet_name='쇼피파이 매출_RAW', header=None)
        self.stdout.write("  쇼피파이 매출 RAW 임포트 중...")

        count = 0
        for i in range(3, len(df)):
            row = df.iloc[i]
            brand = safe_str(row[1])
            if not brand or brand == '없음':
                continue
            date_val = safe_date(row[3])
            if date_val is None:
                continue

            ShopifyOrder.objects.create(
                brand=brand,
                final_amount=safe_decimal(row[2], None),
                order_date=date_val,
                order_name=safe_str(row[4]),
                email=safe_str(row[5]),
                financial_status=safe_str(row[6]),
                subtotal=safe_decimal(row[12], None),
                shipping_cost=safe_decimal(row[13], None),
                taxes=safe_decimal(row[14], None),
                total=safe_decimal(row[15], None),
                discount_code=safe_str(row[16]),
                discount_amount=safe_decimal(row[17], None),
                lineitem_quantity=safe_int(row[20]),
                lineitem_name=safe_str(row[21]),
                lineitem_price=safe_decimal(row[22], None),
                lineitem_sku=safe_str(row[23]),
                shipping_city=safe_str(row[43]),
                shipping_province=safe_str(row[45]),
                shipping_country=safe_str(row[46]),
                shipping_zip=safe_str(row[44]),
            )
            count += 1
        self.stdout.write(f"    → {count}건 임포트 완료")

    @transaction.atomic
    def _import_tiktok_raw(self, xls):
        """틱톡샵 RAW 데이터 임포트"""
        df = pd.read_excel(xls, sheet_name='틱톡샵 매출_RAW', header=None)
        self.stdout.write("  틱톡샵 매출 RAW 임포트 중...")

        count = 0
        for i in range(3, len(df)):
            row = df.iloc[i]
            brand = safe_str(row[1])
            if not brand or brand == '없음':
                continue
            date_val = safe_date(row[3])
            if date_val is None:
                continue

            TiktokOrder.objects.create(
                brand=brand,
                final_amount=safe_decimal(row[2], None),
                order_date=date_val,
                cancel_date=safe_date(row[4]),
                order_id=safe_str(row[5]),
                order_status=safe_str(row[6]),
                seller_sku=safe_str(row[11]),
                product_name=safe_str(row[12]),
                quantity=safe_int(row[14]),
                unit_price=safe_decimal(row[16], None),
                order_amount=safe_decimal(row[28], None),
                refund_amount=safe_decimal(row[29], None),
                shipping_state=safe_str(row[51]),
                shipping_city=safe_str(row[52]),
                shipping_country=safe_str(row[50]),
            )
            count += 1
        self.stdout.write(f"    → {count}건 임포트 완료")

    @transaction.atomic
    def _import_tax(self, xls):
        """세금 데이터 임포트"""
        df = pd.read_excel(xls, sheet_name='Tax_TT', header=None)
        self.stdout.write("  Tax_TT 임포트 중...")

        # 헤더에서 날짜 컬럼 파악 (row 2, cols 2+)
        dates = []
        for col in range(2, len(df.columns)):
            d = safe_date(df.iloc[2, col])
            if d:
                dates.append((col, d))

        count = 0
        for i in range(3, len(df)):
            state = safe_str(df.iloc[i, 1])
            if not state:
                continue
            for col, d in dates:
                amt = safe_decimal(df.iloc[i, col])
                if amt != 0:
                    TaxByState.objects.update_or_create(
                        state_code=state, year=d.year, month=d.month,
                        defaults={'amount': amt}
                    )
                    count += 1
        self.stdout.write(f"    → {count}건 임포트 완료")

    def _parse_month(self, month_str):
        month_map = {
            '1월': 1, '2월': 2, '3월': 3, '4월': 4, '5월': 5, '6월': 6,
            '7월': 7, '8월': 8, '9월': 9, '10월': 10, '11월': 11, '12월': 12,
        }
        return month_map.get(month_str, 1)
