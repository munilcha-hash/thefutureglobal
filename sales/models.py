from django.db import models


class ExchangeRate(models.Model):
    """월별 환율"""
    year = models.IntegerField(verbose_name='연도')
    month = models.IntegerField(verbose_name='월')
    rate = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='환율 (KRW/USD)')

    class Meta:
        unique_together = ('year', 'month')
        ordering = ['year', 'month']
        verbose_name = '환율'
        verbose_name_plural = '환율'

    def __str__(self):
        return f"{self.year}-{self.month:02d}: {self.rate}"


class Brand(models.Model):
    """브랜드"""
    BRAND_CHOICES = [
        ('doctorblet', '닥터블릿'),
        ('pooeng', '푸응'),
        ('delinoshi', '딜리노쉬'),
        ('calo', 'Calo'),
    ]
    code = models.CharField(max_length=20, unique=True, verbose_name='코드')
    name = models.CharField(max_length=50, verbose_name='브랜드명')
    name_kr = models.CharField(max_length=50, verbose_name='브랜드명(한글)')

    class Meta:
        verbose_name = '브랜드'
        verbose_name_plural = '브랜드'

    def __str__(self):
        return self.name_kr


class DailySalesTotal(models.Model):
    """일별 전체 매출/손익 (손익관리 시트 - 전체)"""
    date = models.DateField(verbose_name='날짜')
    year = models.IntegerField(verbose_name='연도')
    month = models.IntegerField(verbose_name='월')

    # 매출
    gmv = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='GMV')
    gsv = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='GSV')

    # 매출원가
    cogs = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='매출원가')

    # 비용
    total_expense = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='비용 합계')
    performance_ad = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='퍼포먼스 광고비')
    influencer_ad = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='인플루언서 광고비')
    sales_commission = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='판매수수료')
    shipping = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='운반비')
    tax = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='세금')

    # 영업이익
    operating_profit = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='영업이익')
    operating_margin = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True, verbose_name='영업이익률')

    class Meta:
        unique_together = ('date',)
        ordering = ['date']
        verbose_name = '일별 전체 손익'
        verbose_name_plural = '일별 전체 손익'

    def __str__(self):
        return f"{self.date} 전체 GSV:{self.gsv:,.0f}"


class DailySalesB2B(models.Model):
    """일별 B2B 매출"""
    date = models.DateField(verbose_name='날짜')
    year = models.IntegerField(verbose_name='연도')
    month = models.IntegerField(verbose_name='월')

    sales_total = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='B2B 합계')
    sales_us = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='미국')
    cogs = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='매출원가')
    total_expense = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='비용 합계')
    shipping = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='운반비')
    tax = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='세금')
    operating_profit = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='영업이익')

    class Meta:
        unique_together = ('date',)
        ordering = ['date']
        verbose_name = '일별 B2B 매출'
        verbose_name_plural = '일별 B2B 매출'


class DailySalesB2C(models.Model):
    """일별 B2C 매출"""
    date = models.DateField(verbose_name='날짜')
    year = models.IntegerField(verbose_name='연도')
    month = models.IntegerField(verbose_name='월')

    # B2C 매출
    b2c_total = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='B2C 합계')
    shopify = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='쇼피파이')
    amazon = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='아마존')
    tiktok = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='틱톡샵')

    # B2C 환불
    refund_shopify = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='환불_쇼피파이')
    refund_amazon = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='환불_아마존')
    refund_tiktok = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='환불_틱톡샵')
    refund_total = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='환불 합계')

    # GSV
    gsv = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='GSV')
    cogs = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='매출원가')

    # 비용
    total_expense = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='비용 합계')
    performance_ad = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='퍼포먼스 광고비')
    influencer_ad = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='인플루언서 광고비')
    sales_commission = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='판매수수료')
    shipping = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='운반비')
    tax = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='세금')

    operating_profit = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='영업이익')
    operating_margin = models.DecimalField(max_digits=8, decimal_places=6, null=True, blank=True, verbose_name='영업이익률')

    class Meta:
        unique_together = ('date',)
        ordering = ['date']
        verbose_name = '일별 B2C 매출'
        verbose_name_plural = '일별 B2C 매출'


class BrandDailySales(models.Model):
    """브랜드별 일별 매출 (닥터블릿/Calo 매출 시트)"""
    date = models.DateField(verbose_name='날짜')
    year = models.IntegerField(verbose_name='연도')
    month = models.IntegerField(verbose_name='월')
    brand = models.ForeignKey(Brand, on_delete=models.CASCADE, verbose_name='브랜드')

    # B2C
    b2c_shopify = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='B2C 쇼피파이')
    b2c_amazon = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='B2C 아마존')
    b2c_tiktok = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='B2C 틱톡샵')
    b2c_total = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='B2C 합계')

    # 환불
    refund_shopify = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='환불 쇼피파이')
    refund_amazon = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='환불 아마존')
    refund_tiktok = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='환불 틱톡샵')
    refund_total = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='환불 합계')

    # GSV
    gsv = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='GSV')

    # B2B
    b2b_us = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='B2B 미국')
    b2b_total = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='B2B 합계')

    # 전체 GSV
    total_gsv = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='전체 GSV')

    # 광고비
    ad_shopify = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='쇼피파이 광고비')
    ad_amazon = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='아마존 광고비')
    ad_tiktok = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='틱톡샵 광고비')

    class Meta:
        unique_together = ('date', 'brand')
        ordering = ['date', 'brand']
        verbose_name = '브랜드별 일별 매출'
        verbose_name_plural = '브랜드별 일별 매출'

    def __str__(self):
        return f"{self.date} {self.brand.name_kr} GSV:{self.total_gsv:,.0f}"


class ShopifyOrder(models.Model):
    """쇼피파이 주문 RAW"""
    brand = models.CharField(max_length=20, verbose_name='브랜드')
    final_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name='최종 매출')
    order_date = models.DateField(null=True, verbose_name='날짜')
    order_name = models.CharField(max_length=50, null=True, blank=True, verbose_name='주문번호')
    email = models.CharField(max_length=200, null=True, blank=True, verbose_name='이메일')
    financial_status = models.CharField(max_length=50, null=True, blank=True, verbose_name='결제상태')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name='소계')
    shipping_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name='배송비')
    taxes = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name='세금')
    total = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name='합계')
    discount_code = models.CharField(max_length=100, null=True, blank=True, verbose_name='할인코드')
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name='할인액')
    lineitem_quantity = models.IntegerField(null=True, verbose_name='수량')
    lineitem_name = models.TextField(null=True, blank=True, verbose_name='상품명')
    lineitem_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name='상품가격')
    lineitem_sku = models.CharField(max_length=50, null=True, blank=True, verbose_name='SKU')
    shipping_city = models.CharField(max_length=100, null=True, blank=True, verbose_name='배송도시')
    shipping_province = models.CharField(max_length=100, null=True, blank=True, verbose_name='배송주')
    shipping_country = models.CharField(max_length=10, null=True, blank=True, verbose_name='배송국가')
    shipping_zip = models.CharField(max_length=20, null=True, blank=True, verbose_name='우편번호')

    class Meta:
        ordering = ['-order_date']
        verbose_name = '쇼피파이 주문'
        verbose_name_plural = '쇼피파이 주문'


class TiktokOrder(models.Model):
    """틱톡샵 주문 RAW"""
    brand = models.CharField(max_length=20, verbose_name='브랜드')
    final_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name='최종 매출')
    order_date = models.DateField(null=True, verbose_name='구매날짜')
    cancel_date = models.DateField(null=True, blank=True, verbose_name='취소날짜')
    order_id = models.CharField(max_length=50, null=True, blank=True, verbose_name='주문ID')
    order_status = models.CharField(max_length=50, null=True, blank=True, verbose_name='주문상태')
    seller_sku = models.CharField(max_length=50, null=True, blank=True, verbose_name='판매자SKU')
    product_name = models.TextField(null=True, blank=True, verbose_name='상품명')
    quantity = models.IntegerField(null=True, verbose_name='수량')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name='단가')
    order_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name='주문금액')
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, verbose_name='환불금액')
    shipping_state = models.CharField(max_length=100, null=True, blank=True, verbose_name='배송주')
    shipping_city = models.CharField(max_length=100, null=True, blank=True, verbose_name='배송도시')
    shipping_country = models.CharField(max_length=50, null=True, blank=True, verbose_name='배송국가')

    class Meta:
        ordering = ['-order_date']
        verbose_name = '틱톡샵 주문'
        verbose_name_plural = '틱톡샵 주문'


class TaxByState(models.Model):
    """주별 세금"""
    state_code = models.CharField(max_length=5, verbose_name='주 코드')
    year = models.IntegerField(verbose_name='연도')
    month = models.IntegerField(verbose_name='월')
    amount = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name='세금액($)')

    class Meta:
        unique_together = ('state_code', 'year', 'month')
        ordering = ['year', 'month', 'state_code']
        verbose_name = '주별 세금'
        verbose_name_plural = '주별 세금'
