from django import template

register = template.Library()

@register.filter
def split(value):
    """Split a string by comma and return a list"""
    if value:
        return [item.strip() for item in value.split(',')]
    return []
