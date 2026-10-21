import unittest

from kathie.providers import ApifyClient, AttioClient, HunterClient, ProviderError


class FakeHTTP:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, method, url, *, headers=None, body=None):
        self.calls.append((method, url, headers, body))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class ProviderTests(unittest.TestCase):
    def test_apify_paginates_and_preserves_source(self):
        http = FakeHTTP(
            [{'firstName': 'Ada', 'lastName': 'L', 'email': 'ADA@EXAMPLE.COM'},
             {'firstName': 'Bob', 'lastName': 'B', 'linkedinUrl': 'https://linkedin.com/in/bob'}],
            [{'firstName': 'Cam', 'lastName': 'C', 'companyWebsite': 'https://example.com'}],
        )
        leads = ApifyClient('secret-test', http, page_size=2).fetch_leads('dataset1', 'tech')
        self.assertEqual(len(leads), 3)
        self.assertEqual(leads[0]['email'], 'ada@example.com')
        self.assertEqual(leads[0]['source'], 'apify')
        self.assertEqual(leads[2]['domain'], 'example.com')
        self.assertIn('offset=2', http.calls[1][1])
        self.assertNotIn('secret-test', http.calls[0][1])
        self.assertEqual(http.calls[0][2]['Authorization'], 'Bearer secret-test')

    def test_actor_schema_mismatch_is_explicit(self):
        with self.assertRaisesRegex(ProviderError, 'row 1'):
            ApifyClient('key', FakeHTTP([{'unexpected': 'shape'}])).fetch_leads('data1', 'tech')

    def test_custom_nested_mapping(self):
        http = FakeHTTP([{'person': {'name': 'Ada'}, 'address': 'ada@example.com'}])
        leads = ApifyClient('key', http, field_map={'first_name': 'person.name', 'email': 'address'}).fetch_leads('data1', 'tech')
        self.assertEqual(leads[0]['first_name'], 'Ada')

    def test_attio_exact_email_and_read_only(self):
        http = FakeHTTP({'data': [{'values': {'email_addresses': [{'email_address': 'ada@example.com'}]}}]})
        self.assertTrue(AttioClient('key', http).contains('ADA@EXAMPLE.COM'))
        method, url, _, body = http.calls[0]
        self.assertEqual(method, 'POST')
        self.assertTrue(url.endswith('/records/query'))
        self.assertEqual(body['filter']['email_addresses'], 'ada@example.com')

    def test_attio_malformed_response_never_means_clear(self):
        with self.assertRaises(ProviderError):
            AttioClient('key', FakeHTTP({'error': 'bad'})).contains('ada@example.com')

    def test_attio_unexpected_filter_result_is_not_clear(self):
        http = FakeHTTP({'data': [{'values': {'email_addresses': [{'email_address': 'other@example.com'}]}}]})
        with self.assertRaises(ProviderError):
            AttioClient('key', http).contains('ada@example.com')

    def test_hunter_finds_email_without_key_in_url(self):
        http = FakeHTTP({'data': {'email': 'ADA@EXAMPLE.COM', 'verification': {'status': 'valid'}, 'sources': []}})
        found = HunterClient('secret-test', http).find_email({'first_name': 'Ada', 'last_name': 'L', 'domain': 'example.com'})
        self.assertEqual(found['email'], 'ada@example.com')
        self.assertEqual(found['status'], 'valid')
        self.assertNotIn('secret-test', http.calls[0][1])

    def test_accept_all_does_not_pass(self):
        http = FakeHTTP({'data': {'status': 'accept_all', 'email': 'ada@example.com'}})
        self.assertEqual(HunterClient('key', http).verify('ada@example.com'), 'unknown')

    def test_malformed_verification_is_visible(self):
        with self.assertRaises(ProviderError):
            HunterClient('key', FakeHTTP({'data': {'surprise': True}})).verify('ada@example.com')

    def test_provider_failure_is_not_clear(self):
        with self.assertRaises(ProviderError):
            AttioClient('key', FakeHTTP(ProviderError('Attio: HTTP 429'))).contains('ada@example.com')


if __name__ == '__main__':
    unittest.main()
