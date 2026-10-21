import unittest
from kathie.attio import AttioClient
from kathie.http import ProviderError


class FakeHTTP:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def record(*emails):
    return {'values': {'email_addresses': [{'email_address': e} for e in emails]}}


class AttioTests(unittest.TestCase):
    def test_exact_normalized_secondary_address_and_read_only_query(self):
        http = FakeHTTP({'data': [record('other@example.com', 'Person@Example.com')]})
        self.assertTrue(AttioClient('fixture', http).contains(' PERSON@example.com '))
        method, url, args = http.calls[0]
        self.assertEqual(method, 'POST')
        self.assertEqual(url, 'https://api.attio.com/v2/objects/people/records/query')
        self.assertEqual(args['body'], {'filter': {'email_addresses': 'person@example.com'}, 'limit': 500, 'offset': 0})
        self.assertEqual(args['headers'], {'Authorization': 'Bearer fixture'})

    def test_empty_complete_query_is_clear(self):
        self.assertFalse(AttioClient('fixture', FakeHTTP({'data': []})).contains('person@example.com'))

    def test_missing_credentials_and_invalid_email_make_no_request(self):
        http = FakeHTTP({'data': []})
        for token, email in [('', 'person@example.com'), ('fixture', 'invalid'), ('fixture', None)]:
            with self.subTest(token=bool(token), email=email):
                with self.assertRaises(ProviderError):
                    AttioClient(token, http).contains(email)
        self.assertEqual(http.calls, [])

    def test_malformed_and_unrelated_results_hold(self):
        for result in [None, [], {}, {'data': {}}, {'data': [None]},
                       {'data': [{'values': {'email_addresses': 'person@example.com'}}]},
                       {'data': [record()]}, {'data': [record('broken')]},
                       {'data': [record('other@example.com')]},
                       {'data': [record('person@example.com'), {}]},
                       {'data': [record('person@example.com')] * 501},
                       {'data': [], 'errors': ['failure']}]:
            with self.subTest(result=result):
                with self.assertRaises(ProviderError):
                    AttioClient('fixture', FakeHTTP(result)).contains('person@example.com')

    def test_provider_failure_propagates(self):
        with self.assertRaisesRegex(ProviderError, 'HTTP 429'):
            AttioClient('fixture', FakeHTTP(ProviderError('Attio: HTTP 429'))).contains('person@example.com')

    def test_full_page_of_unrelated_records_never_clears(self):
        with self.assertRaises(ProviderError):
            AttioClient('fixture', FakeHTTP({'data': [record('other@example.com')] * 500})).contains('person@example.com')
