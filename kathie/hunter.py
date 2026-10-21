"""Hunter acquisition and verification; uncertain results never clear screening."""
from __future__ import annotations

import re
from urllib.parse import urlencode, urlparse

from .http import JsonHTTP, ProviderError, domain_name, normalize_email


class HunterClient:
    def __init__(self, token, http=None):
        self.token = token
        self.http = http or JsonHTTP()

    def _call(self, endpoint, params):
        if not self.token:
            raise ProviderError('Set HUNTER_API_KEY in .env to acquire or verify emails.')
        result = self.http.request('GET', f'https://api.hunter.io/v2/{endpoint}?{urlencode(params)}',
            headers={'Authorization': f'Bearer {self.token}'})
        if not isinstance(result, dict) or not isinstance(result.get('data'), dict):
            raise ProviderError('Hunter: unexpected response; email acquisition/verification is incomplete.')
        return result['data']

    @staticmethod
    def _status(status):
        if status not in ('valid', 'invalid', 'accept_all', 'webmail', 'disposable', 'unknown', 'pending'):
            raise ProviderError('Hunter: missing or unrecognized verification status.')
        return status if status in ('valid', 'invalid') else 'unknown'

    @staticmethod
    def _text(lead, key):
        value = lead.get(key, '')
        if value is None:
            return ''
        if not isinstance(value, str):
            raise ProviderError(f'Hunter: {key} must be text.')
        return value.strip()

    @classmethod
    def _finder_params(cls, lead):
        if not isinstance(lead, dict):
            raise ProviderError('Hunter: email lookup needs a lead object.')
        domain = domain_name(lead.get('domain', ''))
        company = cls._text(lead, 'company') or cls._text(lead, 'company_name')
        first, last = cls._text(lead, 'first_name'), cls._text(lead, 'last_name')
        full_name = cls._text(lead, 'full_name')
        # Prefer the existing name/domain contract when available.
        if (domain or company) and ((first and last) or full_name):
            params = {'domain': domain} if domain else {'company': company}
            params.update({'first_name': first, 'last_name': last} if first and last else {'full_name': full_name})
            return params
        handle = cls._text(lead, 'linkedin_handle')
        profile = cls._text(lead, 'profile_url') or cls._text(lead, 'linkedin_url')
        if not handle and profile:
            parsed = urlparse(profile)
            match = re.fullmatch(r'/in/([^/]+)/?', parsed.path)
            if parsed.scheme not in ('https', 'http') or parsed.hostname not in ('linkedin.com', 'www.linkedin.com') or not match:
                raise ProviderError('Hunter: LinkedIn profile must be a linkedin.com/in/ profile URL.')
            handle = match.group(1)
        if handle:
            if not re.fullmatch(r'[A-Za-z0-9_%.-]+', handle):
                raise ProviderError('Hunter: LinkedIn handle is malformed.')
            return {'linkedin_handle': handle}
        raise ProviderError('Email lookup needs name and company/domain, or a LinkedIn profile.')

    def find_email(self, lead):
        result = self._call('email-finder', self._finder_params(lead))
        if result.get('email') is None:
            return {'email': '', 'status': 'unknown', 'sources': []}
        verification = result.get('verification')
        if not isinstance(verification, dict):
            raise ProviderError('Hunter: found an email without verification evidence.')
        sources = result.get('sources', [])
        if not isinstance(sources, list) or any(not isinstance(source, dict) for source in sources):
            raise ProviderError('Hunter: email source evidence is malformed.')
        return {'email': normalize_email(result['email']), 'status': self._status(verification.get('status')),
            'sources': sources, 'verification': verification}

    def verify(self, email):
        email = normalize_email(email)
        result = self._call('email-verifier', {'email': email})
        if result.get('email') and normalize_email(result['email']) != email:
            raise ProviderError('Hunter: verifier returned a different email; screening is incomplete.')
        return self._status(result.get('status'))
