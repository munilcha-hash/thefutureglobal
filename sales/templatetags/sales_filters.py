from django import template
from decimal import Decimal

register = template.Library()

@register.filter
def krw(value):
    """KRW 포맷 (원)"""
    if value is None:
        return '-'
    try:
        v = float(value)
        if v < 0:
            return f'-₩{abs(v):,.0f}'
        return f'₩{v:,.0f}'
    except (ValueError, TypeError):
        return '-'

@register.filter
def usd(value):
    """USD 포맷"""
    if value is None:
        return '-'
    try:
        v = float(value)
        if v < 0:
            return f'-${abs(v):,.2f}'
        return f'${v:,.2f}'
    except (ValueError, TypeError):
        return '-'

@register.filter
def pct(value):
    """퍼센트 포맷"""
    if value is None:
        return '-'
    try:
        return f'{float(value)*100:.1f}%'
    except (ValueError, TypeError):
        return '-'

@register.filter
def num(value):
    """숫자 포맷 (천단위 콤마)"""
    if value is None:
        return '-'
    try:
        v = float(value)
        if v < 0:
            return f'-{abs(v):,.0f}'
        return f'{v:,.0f}'
    except (ValueError, TypeError):
        return '-'

@register.filter
def month_name(value):
    """월 숫자를 이름으로"""
    try:
        return f'{int(value)}월'
    except (ValueError, TypeError):
        return value
