from django import template

from core.format_utils import format_quantity as format_quantity_value


register = template.Library()


@register.filter
def get_item(mapping, key):
    if mapping is None:
        return ""
    return mapping.get(key, "")


@register.filter
def field_label(value):
    return str(value).replace("_", " ").title()


@register.filter
def format_quantity(value):
    return format_quantity_value(value)
