from __future__ import annotations

import re

from .system_settings import get_setting, set_setting


CLASSIC_HEADER_COLOR_KEY = "classic_header_color"
CLASSIC_HEADER_ALIGNMENT_KEY = "classic_header_alignment"
CLASSIC_COMPANY_NAME_FONT_SIZE_KEY = "classic_company_name_font_size"
CLASSIC_COMPANY_ADDRESS_FONT_SIZE_KEY = "classic_company_address_font_size"
DEFAULT_CLASSIC_HEADER_COLOR = "#111111"
DEFAULT_CLASSIC_HEADER_ALIGNMENT = "right"
DEFAULT_CLASSIC_COMPANY_NAME_FONT_SIZE = 18
DEFAULT_CLASSIC_COMPANY_ADDRESS_FONT_SIZE = 10
ALLOWED_CLASSIC_HEADER_ALIGNMENTS = {"left", "right", "center"}
HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def normalize_classic_header_color(value, default=DEFAULT_CLASSIC_HEADER_COLOR):
    value = str(value or "").strip()
    return value if HEX_COLOR_RE.match(value) else default


def normalize_classic_header_alignment(value):
    value = str(value or "").strip().lower()
    return value if value in ALLOWED_CLASSIC_HEADER_ALIGNMENTS else DEFAULT_CLASSIC_HEADER_ALIGNMENT


def normalize_font_size(value, default, min_value, max_value):
    try:
        size = int(str(value or "").strip())
    except (TypeError, ValueError):
        return default
    return size if min_value <= size <= max_value else default


def scoped_key(key, company_id=None, branch_id=None):
    if company_id and branch_id:
        return f"{key}_{company_id}_{branch_id}"
    if company_id:
        return f"{key}_{company_id}"
    return key


def get_classic_print_settings(company_id=None, branch_id=None):
    color = (
        get_setting(scoped_key(CLASSIC_HEADER_COLOR_KEY, company_id, branch_id))
        or get_setting(scoped_key(CLASSIC_HEADER_COLOR_KEY, company_id))
        or get_setting(CLASSIC_HEADER_COLOR_KEY)
    )
    alignment = (
        get_setting(scoped_key(CLASSIC_HEADER_ALIGNMENT_KEY, company_id, branch_id))
        or get_setting(scoped_key(CLASSIC_HEADER_ALIGNMENT_KEY, company_id))
        or get_setting(CLASSIC_HEADER_ALIGNMENT_KEY)
    )
    name_font_size = (
        get_setting(scoped_key(CLASSIC_COMPANY_NAME_FONT_SIZE_KEY, company_id, branch_id))
        or get_setting(scoped_key(CLASSIC_COMPANY_NAME_FONT_SIZE_KEY, company_id))
        or get_setting(CLASSIC_COMPANY_NAME_FONT_SIZE_KEY)
    )
    address_font_size = (
        get_setting(scoped_key(CLASSIC_COMPANY_ADDRESS_FONT_SIZE_KEY, company_id, branch_id))
        or get_setting(scoped_key(CLASSIC_COMPANY_ADDRESS_FONT_SIZE_KEY, company_id))
        or get_setting(CLASSIC_COMPANY_ADDRESS_FONT_SIZE_KEY)
    )
    return {
        "classic_header_color": normalize_classic_header_color(color),
        "classic_header_alignment": normalize_classic_header_alignment(alignment),
        "classic_company_name_font_size": normalize_font_size(
            name_font_size,
            DEFAULT_CLASSIC_COMPANY_NAME_FONT_SIZE,
            12,
            30,
        ),
        "classic_company_address_font_size": normalize_font_size(
            address_font_size,
            DEFAULT_CLASSIC_COMPANY_ADDRESS_FONT_SIZE,
            8,
            16,
        ),
    }


def set_classic_print_settings(company_id, branch_id, color, alignment, name_font_size=None, address_font_size=None):
    cleaned_color = normalize_classic_header_color(color)
    cleaned_alignment = normalize_classic_header_alignment(alignment)
    cleaned_name_font_size = normalize_font_size(
        name_font_size,
        DEFAULT_CLASSIC_COMPANY_NAME_FONT_SIZE,
        12,
        30,
    )
    cleaned_address_font_size = normalize_font_size(
        address_font_size,
        DEFAULT_CLASSIC_COMPANY_ADDRESS_FONT_SIZE,
        8,
        16,
    )
    set_setting(scoped_key(CLASSIC_HEADER_COLOR_KEY, company_id, branch_id), cleaned_color)
    set_setting(scoped_key(CLASSIC_HEADER_ALIGNMENT_KEY, company_id, branch_id), cleaned_alignment)
    set_setting(scoped_key(CLASSIC_COMPANY_NAME_FONT_SIZE_KEY, company_id, branch_id), str(cleaned_name_font_size))
    set_setting(scoped_key(CLASSIC_COMPANY_ADDRESS_FONT_SIZE_KEY, company_id, branch_id), str(cleaned_address_font_size))
    return {
        "classic_header_color": cleaned_color,
        "classic_header_alignment": cleaned_alignment,
        "classic_company_name_font_size": cleaned_name_font_size,
        "classic_company_address_font_size": cleaned_address_font_size,
    }
