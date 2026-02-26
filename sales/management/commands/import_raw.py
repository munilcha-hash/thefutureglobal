"""
플랫폼별 RAW 데이터 파일(CSV/Excel)을 DB로 임포트하는 관리 커맨드.
파일명에서 플랫폼을 자동 감지하거나 --platform으로 지정 가능.
bulk_create 사용으로 대용량 파일도 빠르게 처리.

Usage:
  python manage.py import_raw path/to/file.csv
  python manage.py import_raw path/to/file.xlsx --platform shopee
"""
import os
import re
import pandas as pd
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from django.core.management.base import BaseCommand
from django.db import transaction
from sales.models import ShopifyOrder, TiktokOrder, ShopeeOrder, Qoo10Order

BATCH_SIZE = 500


def safe_decimal(val, default=0):
    if pd.isna(val) or val is None or val == '' or val == '-':
        return Decimal(str(default)) if default is not None else None
    try:
        cleaned = str(val).replace(',', '').replace('$', '').replace('\t', '').strip()
        if not cleaned or cleaned == '-':
            return Decimal(str(default)) if default is not None else None
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal(str(default)) if default is not None else None


def safe_str(val, default=''):
    if pd.isna(val) or val is None:
        return default
    return str(val).replace('\t', '').strip()


def safe_int(val, default=0):
    if pd.isna(val) or val is None:
        return default
    try:
        return int(float(str(val).replace(',', '').replace('\t', '').strip()))
    except (ValueError, TypeError):
        return default


def safe_date(val):
    """다양한 날짜 형식 파싱"""
    if pd.isna(val) or val is None:
        return None
    if isinstance(val, (datetime, date)):
        if isinstance(val, datetime):
            return val.date()
        return val
    s = str(val).replace('\t', '').strip()
    if not s:
        return None
    formats = [
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
        '%m/%d/%Y %I:%M:%S %p',
        '%m/%d/%Y %H:%M:%S',
        '%m/%d/%Y',
        '%d-%m-%Y %H:%M',
        '%d-%m-%Y',
    ]
    # 시간대 정보 제거 후 파싱
    clean = s.split('+')[0].strip()
    # -0500 같은 UTC 오프셋 제거
    clean = re.sub(r'\s*-\d{4}$', '', clean)
    for fmt in formats:
        try:
            return datetime.strptime(clean, fmt).date()
        except ValueError:
            continue
    return None


def detect_platform(filename):
    """파일명에서 플랫폼 자동 감지"""
    fname = filename.lower()
    if 'orders_export' in fname or '쇼피파이' in fname or 'shopify' in fname:
        return 'shopify'
    if 'all order' in fname or 'all_order' in fname or '틱톡' in fname or 'tiktok' in fname:
        return 'tiktok'
    if 'shopee' in fname or 'shop-stats' in fname or '쇼피' in fname:
        return 'shopee'
    if 'qoo10' in fname or 'transaction' in fname or '큐텐' in fname:
        return 'qoo10'
    return None


def extract_date_from_filename(filename):
    """파일명에서 날짜 추출 (YYYYMMDD 패턴)"""
    matches = re.findall(r'(\d{8})', filename)
    if matches:
        try:
            return datetime.strptime(matches[0], '%Y%m%d').date()
        except ValueError:
            pass
    return None


def extract_brand_from_shopee_filename(filename):
    """Shopee 파일명에서 브랜드 추출 (e.g., drblet.sg.shopee → drblet)"""
    match = re.search(r'_([a-zA-Z]+)\.\w+\.shopee', filename)
    if match:
        brand = match.group(1)
        brand_mapping = {
            'drblet': '닥터블릿',
            'doctorblet': '닥터블릿',
            'eoa': 'EOA',
            'nothingviral': '낫띵베럴',
            'nothingbetter': '낫띵베럴',
            'tetracure': '테트라큐어',
            'calo': 'Calo',
        }
        return brand_mapping.get(brand.lower(), brand)
    return ''


class Command(BaseCommand):
    help = '플랫폼별 RAW 데이터 파일(CSV/Excel)을 DB로 임포트'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='RAW 데이터 파일 경로 (.csv 또는 .xlsx)')
        parser.add_argument('--platform', type=str, default=None,
                            choices=['shopify', 'tiktok', 'shopee', 'qoo10'],
                            help='플랫폼 (미지정시 파일명에서 자동 감지)')
        parser.add_argument('--clear-date', action='store_true',
                            help='해당 날짜 범위의 기존 데이터 삭제 후 임포트')

    def handle(self, *args, **options):
        file_path = options['file_path']
        filename = os.path.basename(file_path)

        platform = options['platform'] or detect_platform(filename)
        if not platform:
            self.stderr.write(self.style.ERROR(
                f'플랫폼을 감지할 수 없습니다: {filename}\n'
                f'--platform 옵션으로 지정해주세요 (shopify, tiktok, shopee, qoo10)'
            ))
            return

        self.stdout.write(f"플랫폼: {platform.upper()} | 파일: {filename}")

        if platform == 'shopify':
            self._import_shopify_csv(file_path, options['clear_date'])
        elif platform == 'tiktok':
            self._import_tiktok_csv(file_path, options['clear_date'])
        elif platform == 'shopee':
            self._import_shopee_excel(file_path, filename, options['clear_date'])
        elif platform == 'qoo10':
            self._import_qoo10_excel(file_path, filename, options['clear_date'])

        self.stdout.write(self.style.SUCCESS(f"[{platform.upper()}] RAW 임포트 완료!"))

    @transaction.atomic
    def _import_shopify_csv(self, file_path, clear_date):
        """Shopify orders_export CSV 임포트 (bulk_create)"""
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False)
        self.stdout.write(f"  Shopify CSV: {len(df)}행 로드됨")

        # 날짜 범위 파악 & 기존 데이터 삭제
        dates = []
        for _, row in df.iterrows():
            d = safe_date(row.get('Paid at') or row.get('Created at'))
            if d:
                dates.append(d)

        if clear_date and dates:
            min_d, max_d = min(dates), max(dates)
            deleted = ShopifyOrder.objects.filter(
                region='us', order_date__gte=min_d, order_date__lte=max_d
            ).delete()[0]
            self.stdout.write(f"  기존 데이터 {deleted}건 삭제 ({min_d} ~ {max_d})")

        objects = []
        for _, row in df.iterrows():
            order_date = safe_date(row.get('Paid at') or row.get('Created at'))
            if not order_date:
                continue

            brand = safe_str(row.get('Vendor', ''))
            name = safe_str(row.get('Name', ''))
            if not name and not brand:
                continue

            total = safe_decimal(row.get('Total'), None)
            subtotal = safe_decimal(row.get('Subtotal'), None)
            final_amount = total if total is not None else subtotal

            objects.append(ShopifyOrder(
                region='us',
                brand=brand,
                final_amount=final_amount,
                order_date=order_date,
                order_name=name,
                email=safe_str(row.get('Email', '')),
                financial_status=safe_str(row.get('Financial Status', '')),
                subtotal=subtotal,
                shipping_cost=safe_decimal(row.get('Shipping'), None),
                taxes=safe_decimal(row.get('Taxes'), None),
                total=total,
                discount_code=safe_str(row.get('Discount Code', '')),
                discount_amount=safe_decimal(row.get('Discount Amount'), None),
                lineitem_quantity=safe_int(row.get('Lineitem quantity', 0)),
                lineitem_name=safe_str(row.get('Lineitem name', '')),
                lineitem_price=safe_decimal(row.get('Lineitem price'), None),
                lineitem_sku=safe_str(row.get('Lineitem sku', '')),
                shipping_city=safe_str(row.get('Shipping City', '')),
                shipping_province=safe_str(row.get('Shipping Province', '') or row.get('Shipping Province Name', '')),
                shipping_country=safe_str(row.get('Shipping Country', '')),
                shipping_zip=safe_str(row.get('Shipping Zip', '')),
            ))

        ShopifyOrder.objects.bulk_create(objects, batch_size=BATCH_SIZE)
        self.stdout.write(f"  → Shopify {len(objects)}건 임포트 완료")

    @transaction.atomic
    def _import_tiktok_csv(self, file_path, clear_date):
        """TikTok All order CSV 임포트 (bulk_create)"""
        df = pd.read_csv(file_path, dtype=str, keep_default_na=False, encoding='utf-8-sig')
        self.stdout.write(f"  TikTok CSV: {len(df)}행 로드됨")

        # 컬럼명 정리 (탭 문자 제거)
        df.columns = [c.replace('\t', '').strip() for c in df.columns]

        # 날짜 범위 파악 & 기존 데이터 삭제
        dates = []
        for _, row in df.iterrows():
            d = safe_date(row.get('Created Time') or row.get('Paid Time'))
            if d:
                dates.append(d)

        if clear_date and dates:
            min_d, max_d = min(dates), max(dates)
            deleted = TiktokOrder.objects.filter(
                region='us', order_date__gte=min_d, order_date__lte=max_d
            ).delete()[0]
            self.stdout.write(f"  기존 데이터 {deleted}건 삭제 ({min_d} ~ {max_d})")

        def detect_tiktok_brand(row):
            sku = safe_str(row.get('Seller SKU', '')).upper()
            product = safe_str(row.get('Product Name', '')).lower()
            if sku.startswith('DR-') or 'dr.blet' in product or 'pooeng' in product:
                return '닥터블릿'
            if sku.startswith('CALO-') or 'calo' in product:
                return 'Calo'
            return ''

        objects = []
        for _, row in df.iterrows():
            order_date = safe_date(row.get('Created Time') or row.get('Paid Time'))
            if not order_date:
                continue

            order_id = safe_str(row.get('Order ID', ''))
            if not order_id:
                continue

            brand = detect_tiktok_brand(row)
            cancel_time = safe_date(row.get('Cancelled Time'))

            sku_subtotal = safe_decimal(row.get('SKU Subtotal After Discount'), None)
            order_amount = safe_decimal(row.get('Order Amount'), None)
            final_amount = sku_subtotal if sku_subtotal is not None else order_amount

            objects.append(TiktokOrder(
                region='us',
                brand=brand,
                final_amount=final_amount,
                order_date=order_date,
                cancel_date=cancel_time,
                order_id=order_id,
                order_status=safe_str(row.get('Order Status', '')),
                seller_sku=safe_str(row.get('Seller SKU', '')),
                product_name=safe_str(row.get('Product Name', '')),
                quantity=safe_int(row.get('Quantity', 0)),
                unit_price=safe_decimal(row.get('SKU Unit Original Price'), None),
                order_amount=order_amount,
                refund_amount=safe_decimal(row.get('Order Refund Amount'), None),
                shipping_state=safe_str(row.get('State', '')),
                shipping_city=safe_str(row.get('City', '')),
                shipping_country=safe_str(row.get('Country', '')),
            ))

        TiktokOrder.objects.bulk_create(objects, batch_size=BATCH_SIZE)
        self.stdout.write(f"  → TikTok {len(objects)}건 임포트 완료")

    @transaction.atomic
    def _import_shopee_excel(self, file_path, filename, clear_date):
        """Shopee shop-stats Excel 임포트 (일별 집계 + 상품별)"""
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True)
        self.stdout.write(f"  Shopee Excel 시트: {wb.sheetnames}")

        file_date = extract_date_from_filename(filename)
        brand = extract_brand_from_shopee_filename(filename)
        self.stdout.write(f"  감지된 날짜: {file_date}, 브랜드: {brand}")

        if clear_date and file_date:
            deleted = ShopeeOrder.objects.filter(
                region='cn', order_date=file_date
            ).delete()[0]
            self.stdout.write(f"  기존 데이터 {deleted}건 삭제 ({file_date})")

        order_date = file_date
        objects = []

        # 1) Placed Order 시트에서 일별 집계 임포트
        if 'Placed Order' in wb.sheetnames:
            ws = wb['Placed Order']
            date_str = str(ws.cell(2, 1).value or '')
            if not order_date and date_str:
                match = re.search(r'(\d{2})-(\d{2})-(\d{4})', date_str)
                if match:
                    day, month, year = match.groups()
                    order_date = date(int(year), int(month), int(day))

            daily_sales = safe_decimal(ws.cell(2, 2).value)
            daily_orders = safe_int(ws.cell(2, 4).value)
            daily_visitors = safe_int(ws.cell(2, 7).value)
            refunded_sales = safe_decimal(ws.cell(2, 12).value)

            if order_date and (daily_sales or daily_orders):
                objects.append(ShopeeOrder(
                    region='cn',
                    brand=brand,
                    final_amount=daily_sales,
                    order_date=order_date,
                    order_id=f'DAILY-{order_date}',
                    order_status='Daily Summary',
                    product_name=f'일별 집계 (주문 {daily_orders}건, 방문자 {daily_visitors}명)',
                    quantity=daily_orders,
                    order_amount=daily_sales,
                    refund_amount=refunded_sales,
                    buyer_country='SG',
                ))
                self.stdout.write(f"  → 일별 집계: 매출 {daily_sales} SGD, 주문 {daily_orders}건")

        # 2) Product Contribution 시트에서 상품별 데이터 임포트
        for sheet_prefix in ['Product Contribution (place', 'Product Contribution (paid']:
            target_sheet = None
            for sname in wb.sheetnames:
                if sname.startswith(sheet_prefix):
                    target_sheet = sname
                    break
            if not target_sheet:
                continue

            ws = wb[target_sheet]
            order_type = 'Placed' if 'place' in target_sheet.lower() else 'Paid'

            i = 5
            while i <= ws.max_row:
                item_id = str(ws.cell(i, 1).value or '')
                product = str(ws.cell(i, 2).value or '')

                if not item_id or item_id in ['Item ID', ''] or not item_id.replace('.', '').isdigit():
                    i += 1
                    continue

                sales = safe_decimal(ws.cell(i, 5).value)
                units = safe_int(ws.cell(i, 9).value)

                if order_date and product:
                    objects.append(ShopeeOrder(
                        region='cn',
                        brand=brand,
                        final_amount=sales,
                        order_date=order_date,
                        order_id=item_id,
                        order_status=order_type,
                        product_name=product,
                        quantity=units,
                        order_amount=sales,
                        buyer_country='SG',
                    ))
                i += 1

        ShopeeOrder.objects.bulk_create(objects, batch_size=BATCH_SIZE)
        self.stdout.write(f"  → Shopee {len(objects)}건 임포트 완료")
        wb.close()

    @transaction.atomic
    def _import_qoo10_excel(self, file_path, filename, clear_date):
        """Qoo10 Transaction Excel 임포트 (bulk_create)"""
        df = pd.read_excel(file_path, sheet_name='data', dtype=str, keep_default_na=False)
        self.stdout.write(f"  Qoo10 Excel: {len(df)}행 로드됨")

        order_date = extract_date_from_filename(filename)
        if not order_date:
            self.stderr.write(self.style.ERROR(
                '파일명에서 날짜를 추출할 수 없습니다. '
                '파일명에 YYYYMMDD 형식의 날짜가 포함되어야 합니다.'
            ))
            return

        self.stdout.write(f"  날짜: {order_date}")

        if clear_date:
            deleted = Qoo10Order.objects.filter(
                region='jp', order_date=order_date
            ).delete()[0]
            self.stdout.write(f"  기존 데이터 {deleted}건 삭제 ({order_date})")

        qoo10_brand_map = {
            'nothingbetter': '낫띵베럴',
            'nothingviral': '낫띵베럴',
            'drblet': '닥터블릿',
            'doctorblet': '닥터블릿',
            'dr.blet': '닥터블릿',
        }

        def detect_qoo10_brand(brand_raw):
            if not brand_raw:
                return ''
            name = brand_raw.split('/')[0].strip().lower()
            return qoo10_brand_map.get(name, brand_raw.split('/')[0].strip())

        objects = []
        for _, row in df.iterrows():
            product_id = safe_str(row.get('상품번호', ''))
            if not product_id:
                continue

            brand_raw = safe_str(row.get('브랜드명', ''))
            brand = detect_qoo10_brand(brand_raw)

            final_amount = safe_decimal(row.get('취소분반영 거래금액'), None)
            order_amount = safe_decimal(row.get('거래금액'), None)
            refund_amount = safe_decimal(row.get('거래취소금액'), None)
            quantity = safe_int(row.get('취소분반영 거래상품수량', 0))

            objects.append(Qoo10Order(
                region='jp',
                brand=brand,
                final_amount=final_amount,
                order_date=order_date,
                order_id=product_id,
                order_status='Transaction',
                product_name=safe_str(row.get('상품명', '')),
                seller_sku=safe_str(row.get('판매자상품코드', '')),
                quantity=quantity,
                order_amount=order_amount,
                refund_amount=refund_amount,
            ))

        Qoo10Order.objects.bulk_create(objects, batch_size=BATCH_SIZE)
        self.stdout.write(f"  → Qoo10 {len(objects)}건 임포트 완료")
