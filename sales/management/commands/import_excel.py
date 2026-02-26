"""
엑셀 파일에서 데이터를 DB로 임포트하는 관리 커맨드.
Usage: python manage.py import_excel path/to/file.xlsx --region us
"""
import pandas as pd
from decimal import Decimal, InvalidOperation
from datetime import datetime
from django.core.management.base import BaseCommand
from django.db import transaction
from sales.models import (
    ExchangeRate, Brand, DailySalesTotal, DailySalesB2B,
    DailySalesB2C, BrandDailySales, ShopifyOrder, TiktokOrder,
    ShopeeOrder, Qoo10Order, TaxByState
)
from sales.region_config import get_region_config


def safe_decimal(val, default=0):
    if pd.isna(val) or val is None or val == '' or val == '#DIV/0!':
        return Decimal(str(default)) if default is not None else None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return Decimal(str(default)) if default is not None else None


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
        parser.add_argument('--region', type=str, default='us',
                            choices=['us', 'cn', 'jp', 'global'],
                            help='지역 코드 (us, cn, jp, global)')
        parser.add_argument('--clear', action='store_true', help='해당 지역 기존 데이터 삭제 후 임포트')

    def handle(self, *args, **options):
        file_path = options['file_path']
        self.region = options['region']
        self.region_config = get_region_config(self.region)

        xls = pd.ExcelFile(file_path)
        self.stdout.write(f"[{self.region}] 시트 목록: {xls.sheet_names}")

        if options['clear']:
            self.stdout.write(f"[{self.region}] 기존 데이터 삭제 중...")
            for model in [DailySalesTotal, DailySalesB2B, DailySalesB2C,
                          BrandDailySales, TaxByState]:
                model.objects.filter(region=self.region).delete()
            ShopifyOrder.objects.filter(region=self.region).delete()
            TiktokOrder.objects.filter(region=self.region).delete()
            ShopeeOrder.objects.filter(region=self.region).delete()
            Qoo10Order.objects.filter(region=self.region).delete()

        self._init_brands()

        # 월별 손익관리 시트 임포트
        for sheet in xls.sheet_names:
            if sheet.startswith('손익관리_'):
                month_str = sheet.replace('손익관리_', '')
                self._import_pnl(xls, sheet, month_str)
            elif sheet.startswith('손익관리 전체_') and self.region == 'global':
                month_str = sheet.replace('손익관리 전체_', '')
                self._import_pnl(xls, sheet, month_str)

        # 브랜드별 매출 시트
        brand_keywords = self.region_config.get('brand_keywords', [])
        for sheet in xls.sheet_names:
            if '매출_' in sheet:
                for kw in brand_keywords:
                    if kw in sheet:
                        self._import_brand_sales(xls, sheet)
                        break

        # RAW 데이터
        raw_sheets = self.region_config.get('raw_sheets', {})
        for sheet_name, channel_type in raw_sheets.items():
            if sheet_name in xls.sheet_names:
                if channel_type == 'shopify':
                    self._import_shopify_raw(xls, sheet_name)
                elif channel_type == 'tiktok':
                    self._import_tiktok_raw(xls, sheet_name)
                elif channel_type == 'shopee':
                    self._import_shopee_raw(xls, sheet_name)
                elif channel_type == 'qoo10':
                    self._import_qoo10_raw(xls, sheet_name)

        # Tax
        tax_sheet = self.region_config.get('tax_sheet')
        if tax_sheet and tax_sheet in xls.sheet_names:
            self._import_tax(xls, tax_sheet)

        self.stdout.write(self.style.SUCCESS(f"[{self.region}] 임포트 완료!"))

    def _init_brands(self):
        brands = self.region_config.get('brands', [])
        for code, name, name_kr in brands:
            Brand.objects.get_or_create(
                code=code, region=self.region,
                defaults={'name': name, 'name_kr': name_kr}
            )

    @transaction.atomic
    def _import_pnl(self, xls, sheet_name, month_str):
        """손익관리 시트 임포트"""
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  [{self.region}] {sheet_name} 임포트 중...")

        rate_val = safe_decimal(df.iloc[1, 2], 1446)
        month_num = self._parse_month(month_str)

        ExchangeRate.objects.update_or_create(
            year=2026, month=month_num, region=self.region,
            defaults={'rate': rate_val}
        )

        for i in range(5, len(df)):
            row = df.iloc[i]
            date_val = safe_date(row[1])
            if date_val is None:
                continue
            if '합계' in str(row[1]):
                break

            DailySalesTotal.objects.update_or_create(
                date=date_val, region=self.region,
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

            DailySalesB2B.objects.update_or_create(
                date=date_val, region=self.region,
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

            b2c_defaults = {
                'year': date_val.year, 'month': date_val.month,
                'b2c_total': safe_decimal(row[25]),
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

            if self.region == 'us':
                b2c_defaults.update({
                    'shopify': safe_decimal(row[26]),
                    'amazon': safe_decimal(row[27]),
                    'tiktok': safe_decimal(row[28]),
                    'refund_shopify': safe_decimal(row[29]),
                    'refund_amazon': safe_decimal(row[30]),
                    'refund_tiktok': safe_decimal(row[31]),
                })
            elif self.region == 'cn':
                b2c_defaults.update({
                    'shopee': safe_decimal(row[26]),
                    'refund_shopee': safe_decimal(row[29]) if len(row) > 29 else Decimal('0'),
                })
            elif self.region == 'jp':
                b2c_defaults.update({
                    'qoo10': safe_decimal(row[26]),
                    'refund_qoo10': safe_decimal(row[29]) if len(row) > 29 else Decimal('0'),
                })

            DailySalesB2C.objects.update_or_create(
                date=date_val, region=self.region,
                defaults=b2c_defaults
            )

        count = DailySalesTotal.objects.filter(month=month_num, region=self.region).count()
        self.stdout.write(f"    → {count}일 데이터 임포트 완료")

    @transaction.atomic
    def _import_brand_sales(self, xls, sheet_name):
        """브랜드 매출 시트 임포트"""
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  [{self.region}] {sheet_name} 임포트 중...")

        brand_map = self.region_config.get('brand_map', {})

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
                brand = Brand.objects.get(code=brand_code, region=self.region)
            except Brand.DoesNotExist:
                continue

            defaults = {
                'year': date_val.year, 'month': date_val.month,
                'b2c_total': safe_decimal(row[6]) if len(row) > 6 else Decimal('0'),
                'refund_total': safe_decimal(row[10]) if len(row) > 10 else Decimal('0'),
                'gsv': safe_decimal(row[11]) if len(row) > 11 else Decimal('0'),
                'b2b_us': safe_decimal(row[15]) if len(row) > 15 else Decimal('0'),
                'b2b_total': safe_decimal(row[16]) if len(row) > 16 else Decimal('0'),
                'total_gsv': safe_decimal(row[17]) if len(row) > 17 else Decimal('0'),
            }

            if self.region == 'us':
                defaults.update({
                    'b2c_shopify': safe_decimal(row[3]),
                    'b2c_amazon': safe_decimal(row[4]) if len(row) > 4 else Decimal('0'),
                    'b2c_tiktok': safe_decimal(row[5]) if len(row) > 5 else Decimal('0'),
                    'refund_shopify': safe_decimal(row[7]) if len(row) > 7 else Decimal('0'),
                    'refund_amazon': safe_decimal(row[8]) if len(row) > 8 else Decimal('0'),
                    'refund_tiktok': safe_decimal(row[9]) if len(row) > 9 else Decimal('0'),
                    'ad_shopify': safe_decimal(row[19]) if len(row) > 19 else Decimal('0'),
                    'ad_amazon': safe_decimal(row[20]) if len(row) > 20 else Decimal('0'),
                    'ad_tiktok': safe_decimal(row[21]) if len(row) > 21 else Decimal('0'),
                })
            elif self.region == 'cn':
                defaults.update({
                    'b2c_shopee': safe_decimal(row[3]),
                    'refund_shopee': safe_decimal(row[7]) if len(row) > 7 else Decimal('0'),
                    'ad_shopee': safe_decimal(row[19]) if len(row) > 19 else Decimal('0'),
                })
            elif self.region == 'jp':
                defaults.update({
                    'b2c_qoo10': safe_decimal(row[3]),
                    'refund_qoo10': safe_decimal(row[7]) if len(row) > 7 else Decimal('0'),
                    'ad_qoo10': safe_decimal(row[19]) if len(row) > 19 else Decimal('0'),
                })

            BrandDailySales.objects.update_or_create(
                date=date_val, brand=brand, region=self.region,
                defaults=defaults
            )

    @transaction.atomic
    def _import_shopify_raw(self, xls, sheet_name='쇼피파이 매출_RAW'):
        """쇼피파이 RAW 데이터 임포트"""
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  [{self.region}] {sheet_name} 임포트 중...")

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
                region=self.region,
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
    def _import_tiktok_raw(self, xls, sheet_name='틱톡샵 매출_RAW'):
        """틱톡샵 RAW 데이터 임포트"""
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  [{self.region}] {sheet_name} 임포트 중...")

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
                region=self.region,
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
    def _import_shopee_raw(self, xls, sheet_name='쇼피 매출_RAW'):
        """쇼피 RAW 데이터 임포트 (China)"""
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  [{self.region}] {sheet_name} 임포트 중...")

        count = 0
        for i in range(3, len(df)):
            row = df.iloc[i]
            brand = safe_str(row[1])
            if not brand or brand == '없음':
                continue
            date_val = safe_date(row[3])
            if date_val is None:
                continue

            ShopeeOrder.objects.create(
                region=self.region,
                brand=brand,
                final_amount=safe_decimal(row[2], None),
                order_date=date_val,
                order_id=safe_str(row[4]) if len(row) > 4 else '',
                order_status=safe_str(row[5]) if len(row) > 5 else '',
                product_name=safe_str(row[6]) if len(row) > 6 else '',
                seller_sku=safe_str(row[7]) if len(row) > 7 else '',
                quantity=safe_int(row[8]) if len(row) > 8 else 0,
                unit_price=safe_decimal(row[9], None) if len(row) > 9 else None,
                order_amount=safe_decimal(row[10], None) if len(row) > 10 else None,
            )
            count += 1
        self.stdout.write(f"    → {count}건 임포트 완료")

    @transaction.atomic
    def _import_qoo10_raw(self, xls, sheet_name='큐텐 매출_RAW'):
        """큐텐 RAW 데이터 임포트 (Japan)"""
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  [{self.region}] {sheet_name} 임포트 중...")

        count = 0
        for i in range(3, len(df)):
            row = df.iloc[i]
            brand = safe_str(row[1])
            if not brand or brand == '없음':
                continue
            date_val = safe_date(row[3])
            if date_val is None:
                continue

            Qoo10Order.objects.create(
                region=self.region,
                brand=brand,
                final_amount=safe_decimal(row[2], None),
                order_date=date_val,
                order_id=safe_str(row[4]) if len(row) > 4 else '',
                order_status=safe_str(row[5]) if len(row) > 5 else '',
                product_name=safe_str(row[6]) if len(row) > 6 else '',
                seller_sku=safe_str(row[7]) if len(row) > 7 else '',
                quantity=safe_int(row[8]) if len(row) > 8 else 0,
                unit_price=safe_decimal(row[9], None) if len(row) > 9 else None,
                order_amount=safe_decimal(row[10], None) if len(row) > 10 else None,
            )
            count += 1
        self.stdout.write(f"    → {count}건 임포트 완료")

    @transaction.atomic
    def _import_tax(self, xls, sheet_name='Tax_TT'):
        """세금 데이터 임포트"""
        df = pd.read_excel(xls, sheet_name=sheet_name, header=None)
        self.stdout.write(f"  [{self.region}] {sheet_name} 임포트 중...")

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
                        state_code=state, year=d.year, month=d.month, region=self.region,
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
