"""Extract observed post authors without asserting audience eligibility."""
from urllib.parse import urlsplit, urlunsplit


CRITERIA = ('location', 'tech_employment', 'school', 'engagement')


def _linkedin_url(value, kind):
    if not isinstance(value, str):
        return ''
    try:
        parsed = urlsplit(value.strip())
        parts = parsed.path.strip('/').split('/')
        if (parsed.scheme != 'https' or parsed.hostname not in ('linkedin.com', 'www.linkedin.com')
                or parsed.username or parsed.password or parsed.port
                or len(parts) != 2 or parts[0] != kind or not parts[1]):
            return ''
    except ValueError:
        return ''
    return urlunsplit(('https', 'www.linkedin.com', '/' + '/'.join(parts), '', ''))


def extract_post_authors(rows, dataset_id, run_id):
    """Return all unique identifiable people and row-level rejection reasons.

    Name splitting is mechanical; notes retain the original display name.
    Duplicate rows retain their source post in the first author's notes.
    """
    if not isinstance(rows, list):
        raise ValueError('Dataset rows must be a list.')
    if any(not isinstance(value, str) or not value.strip() for value in (dataset_id, run_id)):
        raise ValueError('Dataset and run IDs are required.')
    leads, rejected, by_profile = [], [], {}
    for index, row in enumerate(rows, 1):
        reason = ''
        author = row.get('author') if isinstance(row, dict) else None
        if not isinstance(author, dict):
            reason = 'missing_author_object'
        elif author.get('type') != 'person':
            reason = 'not_person_author'
        elif not isinstance(author.get('name'), str) or not author['name'].strip():
            reason = 'missing_author_name'
        else:
            profile = _linkedin_url(author.get('url'), 'in')
            source_post = _linkedin_url(row.get('url'), 'posts')
            if not profile:
                reason = 'invalid_person_profile_url'
            elif not source_post:
                reason = 'missing_or_invalid_source_post_url'
        if reason:
            rejected.append({'row': index, 'reason': reason})
            continue
        name = ' '.join(author['name'].split())
        evidence = f'Post author: {name}; source post: {source_post}; dataset: {dataset_id}; run: {run_id}.'
        if profile in by_profile:
            existing = by_profile[profile]
            if evidence not in existing['notes']:
                existing['notes'] += '\n' + evidence
            rejected.append({'row': index, 'reason': 'duplicate_profile', 'profile_url': profile})
            continue
        names = name.split(' ', 1)
        lead = {
            'first_name': names[0], 'last_name': names[1] if len(names) > 1 else '',
            'profile_url': profile, 'domain': '', 'email': '', 'source': 'apify',
            'source_id': f'{dataset_id}:author:{profile}', 'segment': 'tech', 'notes': evidence,
            'audience': {'status': 'unverified', 'missing': list(CRITERIA),
                         'checks': dict.fromkeys(CRITERIA)},
        }
        leads.append(lead)
        by_profile[profile] = lead
    return {'leads': leads, 'rejected': rejected}
