from django import template

from core.format_utils import amount_in_words as amount_in_words_value
from core.format_utils import format_amount as format_amount_value
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


@register.filter
def format_amount(value):
    return format_amount_value(value)


@register.filter
def amount_in_words(value):
    return amount_in_words_value(value)
