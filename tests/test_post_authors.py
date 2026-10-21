import unittest

from kathie.post_authors import extract_post_authors


def post(name='Ada Lovelace', profile='https://www.linkedin.com/in/ada', **updates):
    row = {'id': '123', 'url': 'https://www.linkedin.com/posts/example-123',
           'author': {'name': name, 'url': profile, 'type': 'person'}}
    row.update(updates)
    return row


class PostAuthorTests(unittest.TestCase):
    def test_person_retains_provenance_and_unknown_audience(self):
        lead = extract_post_authors([post()], 'dataset', 'run')['leads'][0]
        self.assertEqual((lead['first_name'], lead['last_name']), ('Ada', 'Lovelace'))
        self.assertEqual(lead['profile_url'], 'https://www.linkedin.com/in/ada')
        self.assertEqual(lead['source'], 'apify')
        self.assertEqual(lead['segment'], 'tech')
        self.assertEqual((lead['domain'], lead['email']), ('', ''))
        for evidence in ('dataset', 'run', 'https://www.linkedin.com/posts/example-123', 'Ada Lovelace'):
            self.assertIn(evidence, lead['notes'])
        self.assertEqual(lead['audience']['status'], 'unverified')
        self.assertEqual(lead['audience']['missing'], ['location', 'tech_employment', 'school', 'engagement'])
        self.assertTrue(all(value is None for value in lead['audience']['checks'].values()))

    def test_duplicate_profile_merges_source_posts(self):
        rows = [post(), post(profile='https://linkedin.com/in/ada/?trk=test',
                             id='456', url='https://www.linkedin.com/posts/example-456')]
        result = extract_post_authors(rows, 'dataset', 'run')
        self.assertEqual(len(result['leads']), 1)
        self.assertIn('example-456', result['leads'][0]['notes'])
        self.assertEqual(result['rejected'][0]['reason'], 'duplicate_profile')

    def test_company_and_untrusted_profile_are_rejected(self):
        rows = [post(author={'name': 'Company', 'type': 'company', 'url': 'https://www.linkedin.com/company/company'}),
                post(profile='https://linkedin.com.evil.test/in/ada'),
                post(profile='https://www.linkedin.com/in/'),
                post(profile='https://www.linkedin.com/in/ada/extra')]
        result = extract_post_authors(rows, 'dataset', 'run')
        self.assertEqual(result['leads'], [])
        self.assertEqual(len(result['rejected']), 4)

    def test_missing_identity_or_source_is_explained(self):
        rows = [None, {}, post(name=''), post(url=''), post(author='bad')]
        result = extract_post_authors(rows, 'dataset', 'run')
        self.assertEqual(result['leads'], [])
        self.assertEqual([item['row'] for item in result['rejected']], [1, 2, 3, 4, 5])
        self.assertTrue(all(item['reason'] for item in result['rejected']))

    def test_single_name_is_preserved_without_invented_surname(self):
        lead = extract_post_authors([post(name='Cher')], 'dataset', 'run')['leads'][0]
        self.assertEqual((lead['first_name'], lead['last_name']), ('Cher', ''))

    def test_inputs_and_provenance_are_required(self):
        for rows, dataset, run in (({}, 'dataset', 'run'), ([], '', 'run'), ([], 'dataset', '')):
            with self.assertRaises(ValueError):
                extract_post_authors(rows, dataset, run)


if __name__ == '__main__':
    unittest.main()
