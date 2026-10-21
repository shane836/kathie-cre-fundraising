"""Read-only Attio presence check for cold-outreach suppression."""
from .http import JsonHTTP, ProviderError, normalize_email


class AttioClient:
    def __init__(self, token, http=None):
        self.token = token
        self.http = http or JsonHTTP()

    def contains(self, email):
        if not self.token:
            raise ProviderError('Attio credentials are missing; supply ATTIO_TOKEN or a complete Attio snapshot.')
        email = normalize_email(email)
        result = self.http.request(
            'POST', 'https://api.attio.com/v2/objects/people/records/query',
            headers={'Authorization': f'Bearer {self.token}'},
            body={'filter': {'email_addresses': email}, 'limit': 500, 'offset': 0},
        )
        if (not isinstance(result, dict) or not isinstance(result.get('data'), list)
                or len(result['data']) > 500 or result.get('errors') or result.get('error')):
            raise ProviderError('Attio: unexpected query response; screening is incomplete.')
        if not result['data']:
            return False
        matches = []
        for record in result['data']:
            try:
                addresses = record['values']['email_addresses']
                if not isinstance(addresses, list) or not addresses:
                    raise TypeError
                matches.extend(normalize_email(item['email_address']) == email for item in addresses)
            except (KeyError, TypeError, ProviderError):
                raise ProviderError('Attio: email fields are malformed; screening is incomplete.') from None
        if any(matches):
            return True
        # This is an equality query: any nonempty unmatched result is an API/filter
        # anomaly. In particular, a full page must never be interpreted as clear.
        raise ProviderError('Attio: query returned unrelated records; check the email filter before clearing leads.')
