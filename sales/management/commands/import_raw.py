"""
플랫폼별 RAW 데이터 파일(CSV/Excel)을 DB로 임포트하는 관리 커맨드.
파일명에서 플랫폼을 자동 감지하거나 --platform으로 지정 가능.

CSV는 Python csv 모듈(경량), Excel은 openpyxl(경량)만 사용 - pandas 미사용.
bulk_create로 대용량도 빠르게 처리.

Usage:
  python manage.py import_raw path/to/file.csv
  python manage.py import_raw path/to/file.xlsx --platform shopee
"""
import csv
import os
import re
from decimal import Decimal, InvalidOperation
from datetime import datetime, date
from django.core.management.base import BaseCommand
from django.db import transaction
from sales.models import ShopifyOrder, TiktokOrder, ShopeeOrder, Qoo10Order

BATCH_SIZE = 500


def safe_decimal(val, default=0):
    if val is None or val == '' or val == '-':
        return Decimal(str(default)) if default is not None else None
    try:
        cleaned = str(val).replace(',', '').replace('$', '').replace('\t', '').strip()
        if not cleaned or cleaned == '-':
            return Decimal(str(default)) if default is not None else None
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return Decimal(str(default)) if default is not None else None


def safe_str(val, default=''):
    if val is None:
        return default
    return str(val).replace('\t', '').strip()


def safe_int(val, default=0):
    if val is None or val == '':
        return default
    try:
        return int(float(str(val).replace(',', '').replace('\t', '').strip()))
    except (ValueError, TypeError):
        return default


def safe_date(val):
    """다양한 날짜 형식 파싱"""
    if val is None:
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
    # 시간대 정보 제거
    clean = s.split('+')[0].strip()
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
    """Shopee 파일명에서 브랜드 추출"""
    match = re.search(r'_([a-zA-Z]+)\.\w+\.shopee', filename)
    if match:
        brand = match.group(1)
        brand_mapping = {
            'drblet': '닥터블릿', 'doctorblet': '닥터블릿',
            'eoa': 'EOA', 'nothingviral': '낫띵베럴',
            'nothingbetter': '낫띵베럴', 'tetracure': '테트라큐어', 'calo': 'Calo',
        }
        return brand_mapping.get(brand.lower(), brand)
    return ''


def _read_csv_rows(file_path):
    """CSV를 경량으로 읽기 (pandas 미사용). 헤더→dict 리스트 반환."""
    rows = []
    # BOM 처리를 위해 utf-8-sig
    with open(file_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        # 헤더 탭 제거
        if reader.fieldnames:
            reader.fieldnames = [h.replace('\t', '').strip() for h in reader.fieldnames]
        for row in reader:
            rows.append(row)
    return rows


class Command(BaseCommand):
    help = '플랫폼별 RAW 데이터 파일(CSV/Excel)을 DB로 임포트'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='RAW 데이터 파일 경로')
        parser.add_argument('--platform', type=str, default=None,
                            choices=['shopify', 'tiktok', 'shopee', 'qoo10'],
                            help='플랫폼 (미지정시 파일명에서 자동 감지)')
        parser.add_argument('--clear-date', action='store_true',
                            help='해당 날짜 범위의 기존 데이터 삭제 후 임포트')
        parser.add_argument('--original-filename', type=str, default=None,
                            help='원본 파일명 (UUID 임시파일 사용 시 날짜/브랜드 추출용)')

    def handle(self, *args, **options):
        file_path = options['file_path']
        # 원본 파일명이 지정되면 그것을 사용, 아니면 실제 파일경로에서 추출
        filename = options['original_filename'] or os.path.basename(file_path)

        platform = options['platform'] or detect_platform(filename)
        if not platform:
            self.stderr.write(self.style.ERROR(
                f'플랫폼을 감지할 수 없습니다: {filename}\n'
                f'--platform 옵션으로 지정해주세요 (shopify, tiktok, shopee, qoo10)'
            ))
            return

        self.stdout.write(f"플랫폼: {platform.upper()} | 파일: {filename}")

        try:
            if platform == 'shopify':
                self._import_shopify_csv(file_path, options['clear_date'])
            elif platform == 'tiktok':
                self._import_tiktok_csv(file_path, options['clear_date'])
            elif platform == 'shopee':
                self._import_shopee_excel(file_path, filename, options['clear_date'])
            elif platform == 'qoo10':
                self._import_qoo10_excel(file_path, filename, options['clear_date'])
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"임포트 오류: {e}"))
            raise

        self.stdout.write(self.style.SUCCESS(f"[{platform.upper()}] RAW 임포트 완료!"))

    @transaction.atomic
    def _import_shopify_csv(self, file_path, clear_date):
        """Shopify orders_export CSV 임포트"""
        rows = _read_csv_rows(file_path)
        self.stdout.write(f"  Shopify CSV: {len(rows)}행 로드됨")

        # 날짜 범위 파악
        dates = []
        for row in rows:
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
        for row in rows:
            order_date = safe_date(row.get('Paid at') or row.get('Created at'))
            if not order_date:
                continue

            brand = safe_str(row.get('Vendor', ''))
            name = safe_str(row.get('Name', ''))
            if not name and not brand:
                continue

            total = safe_decimal(row.get('Total'), None)
            subtotal = safe_decimal(row.get('Subtotal'), None)

            objects.append(ShopifyOrder(
                region='us',
                brand=brand,
                final_amount=total if total is not None else subtotal,
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
        """TikTok All order CSV 임포트"""
        rows = _read_csv_rows(file_path)
        self.stdout.write(f"  TikTok CSV: {len(rows)}행 로드됨")

        # 날짜 범위 파악
        dates = []
        for row in rows:
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
        for row in rows:
            order_date = safe_date(row.get('Created Time') or row.get('Paid Time'))
            if not order_date:
                continue

            order_id = safe_str(row.get('Order ID', ''))
            if not order_id:
                continue

            sku_subtotal = safe_decimal(row.get('SKU Subtotal After Discount'), None)
            order_amount = safe_decimal(row.get('Order Amount'), None)

            objects.append(TiktokOrder(
                region='us',
                brand=detect_tiktok_brand(row),
                final_amount=sku_subtotal if sku_subtotal is not None else order_amount,
                order_date=order_date,
                cancel_date=safe_date(row.get('Cancelled Time')),
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
        """Shopee shop-stats Excel 임포트"""
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
                    region='cn', brand=brand, final_amount=daily_sales,
                    order_date=order_date, order_id=f'DAILY-{order_date}',
                    order_status='Daily Summary',
                    product_name=f'일별 집계 (주문 {daily_orders}건, 방문자 {daily_visitors}명)',
                    quantity=daily_orders, order_amount=daily_sales,
                    refund_amount=refunded_sales, buyer_country='SG',
                ))

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

            for i in range(5, ws.max_row + 1):
                item_id = str(ws.cell(i, 1).value or '')
                product = str(ws.cell(i, 2).value or '')
                if not item_id or not item_id.replace('.', '').isdigit():
                    continue
                sales = safe_decimal(ws.cell(i, 5).value)
                units = safe_int(ws.cell(i, 9).value)
                if order_date and product:
                    objects.append(ShopeeOrder(
                        region='cn', brand=brand, final_amount=sales,
                        order_date=order_date, order_id=item_id,
                        order_status=order_type, product_name=product,
                        quantity=units, order_amount=sales, buyer_country='SG',
                    ))

        ShopeeOrder.objects.bulk_create(objects, batch_size=BATCH_SIZE)
        self.stdout.write(f"  → Shopee {len(objects)}건 임포트 완료")
        wb.close()

    @transaction.atomic
    def _import_qoo10_excel(self, file_path, filename, clear_date):
        """Qoo10 Transaction Excel 임포트"""
        import openpyxl
        wb = openpyxl.load_workbook(file_path, data_only=True)
        ws = wb['data']
        self.stdout.write(f"  Qoo10 Excel: {ws.max_row - 1}행 로드됨")

        order_date = extract_date_from_filename(filename)
        if not order_date:
            self.stderr.write(self.style.ERROR('파일명에서 날짜를 추출할 수 없습니다.'))
            wb.close()
            return

        self.stdout.write(f"  날짜: {order_date}")

        if clear_date:
            deleted = Qoo10Order.objects.filter(
                region='jp', order_date=order_date
            ).delete()[0]
            self.stdout.write(f"  기존 데이터 {deleted}건 삭제 ({order_date})")

        qoo10_brand_map = {
            'nothingbetter': '낫띵베럴', 'nothingviral': '낫띵베럴',
            'drblet': '닥터블릿', 'doctorblet': '닥터블릿', 'dr.blet': '닥터블릿',
        }

        # 헤더 읽기 (row 1)
        headers = [str(ws.cell(1, c).value or '') for c in range(1, ws.max_column + 1)]
        col = {h: i for i, h in enumerate(headers)}

        objects = []
        for r in range(2, ws.max_row + 1):
            vals = [ws.cell(r, c).value for c in range(1, ws.max_column + 1)]
            product_id = safe_str(vals[col.get('상품번호', 0)])
            if not product_id:
                continue

            brand_raw = safe_str(vals[col.get('브랜드명', 3)])
            name = brand_raw.split('/')[0].strip().lower() if brand_raw else ''
            brand = qoo10_brand_map.get(name, brand_raw.split('/')[0].strip() if brand_raw else '')

            objects.append(Qoo10Order(
                region='jp', brand=brand,
                final_amount=safe_decimal(vals[col.get('취소분반영 거래금액', 6)], None),
                order_date=order_date,
                order_id=product_id,
                order_status='Transaction',
                product_name=safe_str(vals[col.get('상품명', 2)]),
                seller_sku=safe_str(vals[col.get('판매자상품코드', 1)]),
                quantity=safe_int(vals[col.get('취소분반영 거래상품수량', 9)]),
                order_amount=safe_decimal(vals[col.get('거래금액', 4)], None),
                refund_amount=safe_decimal(vals[col.get('거래취소금액', 5)], None),
            ))

        Qoo10Order.objects.bulk_create(objects, batch_size=BATCH_SIZE)
        self.stdout.write(f"  → Qoo10 {len(objects)}건 임포트 완료")
        wb.close()
