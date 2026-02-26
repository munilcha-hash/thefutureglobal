"""
Region configuration for multi-region sales management.
Each region has its own brands, channels, and Excel sheet naming conventions.
"""

REGION_CHOICES = [
    ('us', '미국'),
    ('cn', '중국'),
    ('jp', '일본'),
    ('global', '전체'),
]

REGION_CONFIG = {
    'us': {
        'name': '미국',
        'name_en': 'US',
        'currency': 'USD',
        'flag': '\U0001F1FA\U0001F1F8',
        'brands': [
            ('doctorblet', 'Dr.Blet', '닥터블릿'),
            ('calo', 'Calo', 'Calo'),
        ],
        'channels': {
            'shopify': 'Shopify',
            'amazon': 'Amazon',
            'tiktok': 'TikTok',
        },
        'channel_fields': ['shopify', 'amazon', 'tiktok'],
        'refund_fields': ['refund_shopify', 'refund_amazon', 'refund_tiktok'],
        'raw_sheets': {
            '쇼피파이 매출_RAW': 'shopify',
            '틱톡샵 매출_RAW': 'tiktok',
        },
        'order_pages': [
            {'url_name': 'shopify_orders', 'icon': 'bi-bag-fill', 'label': 'Shopify 주문'},
            {'url_name': 'tiktok_orders', 'icon': 'bi-tiktok', 'label': 'TikTok 주문'},
        ],
        'tax_sheet': 'Tax_TT',
        'brand_keywords': ['닥터블릿', 'Calo'],
        'brand_map': {
            '닥터블릿': 'doctorblet',
            'Calo': 'calo',
        },
    },
    'cn': {
        'name': '중국',
        'name_en': 'China',
        'currency': 'CNY',
        'flag': '\U0001F1E8\U0001F1F3',
        'brands': [
            ('doctorblet', 'Dr.Blet', '닥터블릿'),
            ('eoa', 'EOA', 'EOA'),
            ('nothingviral', 'Nothing Viral', '낫띵베럴'),
            ('tetracure', 'Tetracure', '테트라큐어'),
        ],
        'channels': {
            'shopee': 'Shopee',
        },
        'channel_fields': ['shopee'],
        'refund_fields': ['refund_shopee'],
        'raw_sheets': {
            '쇼피 매출_RAW': 'shopee',
        },
        'order_pages': [
            {'url_name': 'shopee_orders', 'icon': 'bi-shop', 'label': 'Shopee 주문'},
        ],
        'tax_sheet': None,
        'brand_keywords': ['닥터블릿', 'EOA', '낫띵베럴', '테트라큐어'],
        'brand_map': {
            '닥터블릿': 'doctorblet',
            'EOA': 'eoa',
            '낫띵베럴': 'nothingviral',
            '테트라큐어': 'tetracure',
        },
    },
    'jp': {
        'name': '일본',
        'name_en': 'Japan',
        'currency': 'JPY',
        'flag': '\U0001F1EF\U0001F1F5',
        'brands': [
            ('doctorblet', 'Dr.Blet', '닥터블릿'),
            ('nothingviral', 'Nothing Viral', '낫띵베럴'),
        ],
        'channels': {
            'qoo10': 'Qoo10',
        },
        'channel_fields': ['qoo10'],
        'refund_fields': ['refund_qoo10'],
        'raw_sheets': {
            '큐텐 매출_RAW': 'qoo10',
        },
        'order_pages': [
            {'url_name': 'qoo10_orders', 'icon': 'bi-cart-fill', 'label': 'Qoo10 주문'},
        ],
        'tax_sheet': None,
        'brand_keywords': ['닥터블릿', '낫띵베럴'],
        'brand_map': {
            '닥터블릿': 'doctorblet',
            '낫띵베럴': 'nothingviral',
        },
    },
    'global': {
        'name': '전체',
        'name_en': 'Global',
        'currency': 'USD',
        'flag': '\U0001F310',
        'brands': [],
        'channels': {},
        'channel_fields': [],
        'refund_fields': [],
        'raw_sheets': {},
        'order_pages': [],
        'tax_sheet': None,
        'pnl_sheet_prefix': '손익관리 전체_',
        'brand_keywords': [],
        'brand_map': {},
    },
}


def get_region_config(region_code):
    """Get config for a specific region, defaulting to US."""
    return REGION_CONFIG.get(region_code, REGION_CONFIG['us'])


def get_all_brand_codes():
    """Get all unique brand codes across all regions."""
    codes = set()
    for config in REGION_CONFIG.values():
        for code, _, _ in config.get('brands', []):
            codes.add(code)
    return codes
