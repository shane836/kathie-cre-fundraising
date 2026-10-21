"""Read-only lead acquisition adapters. No email delivery lives here."""
from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class ProviderError(RuntimeError):
    """A safe, actionable provider failure without secrets or response bodies."""


class JsonHTTP:
    def __init__(self, accepted_statuses=(200,)):
        self.accepted_statuses = accepted_statuses

    def request(self, method, url, *, headers=None, body=None):
        request = Request(
            url, method=method,
            headers={'Accept': 'application/json', 'Content-Type': 'application/json', **(headers or {})},
            data=json.dumps(body).encode() if body is not None else None,
        )
        provider = urlparse(url).hostname
        try:
            with urlopen(request, timeout=30) as response:
                if response.status not in self.accepted_statuses:
                    raise ProviderError(f'{provider}: HTTP {response.status}; request is incomplete. Try again after review.')
                return json.loads(response.read())
        except HTTPError as exc:
            raise ProviderError(f'{provider}: HTTP {exc.code}; check credentials, limits, and provider status.') from None
        except (URLError, TimeoutError, OSError):
            raise ProviderError(f'{provider}: connection failed or timed out; request outcome is uncertain.') from None
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise ProviderError(f'{provider}: response was not valid JSON.') from None


def normalize_email(value):
    if not isinstance(value, str) or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+', value.strip()):
        raise ProviderError('Email address is missing or malformed.')
    return value.strip().lower()


def domain_name(value):
    if not value:
        return ''
    if not isinstance(value, str):
        raise ProviderError('Company website/domain must be text.')
    parsed = urlparse(value.strip() if '://' in value else 'https://' + value.strip())
    host = parsed.hostname or ''
    return host.lower().removeprefix('www.')


def nested(row, path):
    value = row
    for key in path.split('.'):
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


