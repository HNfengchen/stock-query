import re
from typing import Any


_SENSITIVE_KEYS = {
    'password', 'passwd', 'pwd', 'secret', 'token', 'access_token',
    'refresh_token', 'api_key', 'apikey', 'private_key', 'credit_card',
    'card_number', 'cvv', 'ssn', 'id_card', 'bank_card', 'phone',
    'mobile', 'email', 'authorization', 'cookie',
}

_MASK = '******'

_PHONE_PATTERN = re.compile(r'1[3-9]\d{9}')
_ID_CARD_PATTERN = re.compile(r'[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx]')
_BANK_CARD_PATTERN = re.compile(r'\b\d{16,19}\b')
_EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')


def mask_value(value: str) -> str:
    if not isinstance(value, str) or len(value) < 3:
        return _MASK
    return value[:2] + _MASK + value[-1:]


def mask_phone(value: str) -> str:
    if _PHONE_PATTERN.fullmatch(value):
        return value[:3] + _MASK + value[-2:]
    return value


def mask_id_card(value: str) -> str:
    if _ID_CARD_PATTERN.fullmatch(value):
        return value[:3] + _MASK + value[-1:]
    return value


def mask_bank_card(value: str) -> str:
    if _BANK_CARD_PATTERN.fullmatch(value):
        return value[:4] + _MASK + value[-4:]
    return value


def mask_email(value: str) -> str:
    if _EMAIL_PATTERN.fullmatch(value):
        parts = value.split('@')
        if len(parts) == 2:
            return parts[0][:2] + _MASK + '@' + parts[1]
    return value


def mask_string_patterns(value: str) -> str:
    if not isinstance(value, str):
        return value
    value = _PHONE_PATTERN.sub(lambda m: m.group()[:3] + _MASK + m.group()[-2:], value)
    value = _ID_CARD_PATTERN.sub(lambda m: m.group()[:3] + _MASK + m.group()[-1:], value)
    value = _BANK_CARD_PATTERN.sub(lambda m: m.group()[:4] + _MASK + m.group()[-4:], value)
    value = _EMAIL_PATTERN.sub(lambda m: m.group()[:2] + _MASK + '@' + m.group().split('@')[1], value)
    return value


def sanitize_data(data: Any, depth: int = 0) -> Any:
    if depth > 10:
        return '...'
    if data is None:
        return None
    if isinstance(data, bool):
        return data
    if isinstance(data, (int, float)):
        return data
    if isinstance(data, str):
        return mask_string_patterns(data)
    if isinstance(data, (list, tuple)):
        return [sanitize_data(item, depth + 1) for item in data]
    if isinstance(data, dict):
        result = {}
        for key, value in data.items():
            key_lower = key.lower() if isinstance(key, str) else str(key).lower()
            if key_lower in _SENSITIVE_KEYS:
                result[key] = _MASK
            elif isinstance(value, str):
                result[key] = mask_string_patterns(value)
            else:
                result[key] = sanitize_data(value, depth + 1)
        return result
    if hasattr(data, '__dict__'):
        return sanitize_data(data.__dict__, depth + 1)
    return str(data)
