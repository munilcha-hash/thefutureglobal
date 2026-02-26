"""
Context processors for region-aware templates.
Provides current_region, region_config, and all_regions to all templates.
"""
from django.urls import reverse
from .region_config import REGION_CONFIG, REGION_CHOICES
from .models import DailySalesTotal


def region_context(request):
    current_region = request.session.get('current_region', 'us')
    config = REGION_CONFIG.get(current_region, REGION_CONFIG['us'])

    # Resolve URLs for order pages
    order_pages_resolved = []
    for page in config.get('order_pages', []):
        try:
            url = reverse(f'sales:{page["url_name"]}')
        except Exception:
            url = '#'
        order_pages_resolved.append({
            'url': url,
            'url_name': page['url_name'],
            'icon': page['icon'],
            'label': page['label'],
        })

    # Get available months for current region
    months = list(
        DailySalesTotal.objects.filter(region=current_region)
        .values('year', 'month').distinct().order_by('year', 'month')
    )

    return {
        'current_region': current_region,
        'region_config': config,
        'all_regions': REGION_CHOICES,
        'order_pages': order_pages_resolved,
        'months': months,
    }
