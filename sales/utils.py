import os
import uuid


def save_upload(f):
    """업로드 파일을 안전한 임시 경로에 저장 (한국어 파일명 회피)"""
    ext = os.path.splitext(f.name)[1].lower()
    safe_name = f'upload_{uuid.uuid4().hex[:8]}{ext}'
    path = f'/tmp/{safe_name}'
    with open(path, 'wb+') as dest:
        for chunk in f.chunks():
            dest.write(chunk)
    return path


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
