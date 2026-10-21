import unittest
from urllib.parse import parse_qs, urlparse
from kathie.hunter import HunterClient
from kathie.http import ProviderError


class FakeHTTP:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self.data


class HunterTests(unittest.TestCase):
    def finder(self, lead, data=None):
        http = FakeHTTP({'data': data or {'email': 'TEST@Example.com', 'verification': {'status': 'valid'}, 'sources': []}})
        result = HunterClient('fixture-token', http).find_email(lead)
        return result, http

    def test_domain_lookup_uses_bearer_without_secret_in_url(self):
        result, http = self.finder({'domain': 'https://www.example.com/a', 'first_name': 'Jane', 'last_name': 'Doe'})
        self.assertEqual(result['email'], 'test@example.com')
        self.assertEqual(parse_qs(urlparse(http.calls[0][1]).query)['domain'], ['example.com'])
        self.assertNotIn('fixture-token', http.calls[0][1])
        self.assertEqual(http.calls[0][2]['headers']['Authorization'], 'Bearer fixture-token')

    def test_linkedin_only_lookup(self):
        _, http = self.finder({'profile_url': 'https://www.linkedin.com/in/jane-doe/?tracking=1'})
        self.assertEqual(parse_qs(urlparse(http.calls[0][1]).query)['linkedin_handle'], ['jane-doe'])

    def test_company_full_name_lookup(self):
        _, http = self.finder({'company': 'Example', 'full_name': 'Jane Doe'})
        self.assertEqual(parse_qs(urlparse(http.calls[0][1]).query)['company'], ['Example'])

    def test_wrong_linkedin_host_not_accepted(self):
        with self.assertRaises(ProviderError):
            self.finder({'profile_url': 'https://evil.example/in/jane-doe'})

    def test_missing_identifiers_fails_without_request(self):
        http = FakeHTTP({})
        with self.assertRaises(ProviderError):
            HunterClient('fixture-token', http).find_email({'first_name': 'Jane'})
        self.assertEqual(http.calls, [])

    def test_catchall_disposable_and_pending_not_valid(self):
        for status in ('accept_all', 'disposable', 'webmail', 'unknown', 'pending'):
            result, _ = self.finder({'linkedin_handle': 'jane-doe'}, {'email': 'jane@example.com', 'verification': {'status': status}})
            self.assertEqual(result['status'], 'unknown')

    def test_no_result_is_unknown(self):
        result, _ = self.finder({'linkedin_handle': 'jane-doe'}, {'email': None})
        self.assertEqual(result, {'email': '', 'status': 'unknown', 'sources': []})

    def test_malformed_sources_fails(self):
        with self.assertRaises(ProviderError):
            self.finder({'linkedin_handle': 'jane-doe'}, {'email': 'jane@example.com', 'verification': {'status': 'valid'}, 'sources': 'bad'})

    def test_verifier_rejects_different_email(self):
        with self.assertRaises(ProviderError):
            HunterClient('fixture-token', FakeHTTP({'data': {'email': 'other@example.com', 'status': 'valid'}})).verify('jane@example.com')

    def test_missing_key_and_malformed_result_fail(self):
        for token, data in [('', {'data': {}}), ('fixture-token', []), ('fixture-token', {'data': []})]:
            with self.assertRaises(ProviderError):
                HunterClient(token, FakeHTTP(data)).verify('jane@example.com')

    def test_unknown_status_fails(self):
        with self.assertRaises(ProviderError):
            HunterClient('fixture-token', FakeHTTP({'data': {'status': 'surprise'}})).verify('jane@example.com')
