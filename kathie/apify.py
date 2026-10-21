"""Apify dataset acquisition and explicitly configured task orchestration."""
import math
import re
from urllib.parse import urlencode
from .http import JsonHTTP, ProviderError, normalize_email, domain_name, nested

class ApifyClient:
    DEFAULT_FIELDS = {
        'first_name': ['firstName', 'first_name'],
        'last_name': ['lastName', 'last_name'],
        'email': ['email', 'emailAddress'],
        'domain': ['companyWebsite', 'domain', 'companyDomain'],
        'profile_url': ['linkedinUrl', 'profileUrl', 'profile_url'],
        'source_id': ['id', 'profileId'],
        'notes': ['headline', 'notes'],
    }

    def __init__(self, token, http=None, page_size=1000, field_map=None):
        self.token = token
        self.http = http or JsonHTTP(accepted_statuses=(200, 201, 202))
        self.page_size = page_size
        self.field_map = {**self.DEFAULT_FIELDS, **(field_map or {})}
        if not isinstance(page_size, int) or page_size < 1:
            raise ValueError('Page size must be positive.')
        if any(key not in self.DEFAULT_FIELDS for key in self.field_map):
            raise ValueError('Unknown Apify mapping field.')
        if any(not isinstance(paths, (str, list)) for paths in self.field_map.values()):
            raise ValueError('Apify mapping values must be field paths or lists of paths.')

    def fetch_leads(self, dataset_id, segment):
        if not self.token:
            raise ProviderError('Set APIFY_TOKEN in .env before importing a dataset.')
        if not re.fullmatch(r'[A-Za-z0-9_-]+', dataset_id or ''):
            raise ProviderError('Enter a dataset ID, not a URL.')
        if segment not in ('tech', 'real_estate'):
            raise ProviderError('Choose a supported investor segment.')
        leads, offset = [], 0
        for _ in range(100):
            query = urlencode({'format': 'json', 'clean': 'true', 'offset': offset, 'limit': self.page_size})
            rows = self.http.request('GET', f'https://api.apify.com/v2/datasets/{dataset_id}/items?{query}', headers={'Authorization': f'Bearer {self.token}'})
            if not isinstance(rows, list) or len(rows) > self.page_size:
                raise ProviderError('Apify: dataset page has an unexpected shape.')
            for index, row in enumerate(rows, start=offset + 1):
                if not isinstance(row, dict):
                    raise ProviderError(f'Apify row {index}: expected a lead object; check field mapping.')
                lead = {}
                for field, paths in self.field_map.items():
                    paths = [paths] if isinstance(paths, str) else paths
                    lead[field] = next((nested(row, path) for path in paths if nested(row, path) not in (None, '')), '')
                if any(not isinstance(value, str) for value in lead.values()):
                    raise ProviderError(f'Apify row {index}: mapped fields must be text; check field mapping.')
                if not any(lead[field] for field in ('email', 'profile_url', 'first_name', 'last_name')):
                    raise ProviderError(f'Apify row {index}: no identity fields; check field mapping.')
                if lead['email']:
                    try:
                        lead['email'] = normalize_email(lead['email'])
                    except ProviderError:
                        raise ProviderError(f'Apify row {index}: malformed email; fix the source row.') from None
                lead['domain'] = domain_name(lead['domain'])
                lead.update(source='apify', segment=segment)
                lead['audience'] = self.audience_evidence(row, segment)
                lead['source_id'] = f"{dataset_id}:{lead['source_id'] or index}"
                leads.append(lead)
            if len(rows) < self.page_size:
                return leads
            offset += len(rows)
        raise ProviderError('Apify: import exceeded 100 pages; split the dataset into smaller batches.')

    @staticmethod
    def audience_evidence(row, segment):
        required = ('location', 'tech_employment', 'school', 'engagement') if segment == 'tech' else ('location', 'real_estate_or_construction')
        supplied = row.get('audience', {})
        if not isinstance(supplied, dict) or not isinstance(supplied.get('checks', {}), dict):
            raise ProviderError('Apify: audience evidence must be an object with checks.')
        checks = {key: supplied.get('checks', {}).get(key) for key in required}
        if any(value is not None and not isinstance(value, bool) for value in checks.values()):
            raise ProviderError('Apify: audience checks must be true, false, or null.')
        missing = [key for key, value in checks.items() if value is None]
        status = 'excluded' if False in checks.values() else 'unverified' if missing else 'verified'
        return {'status': status, 'missing': missing, 'checks': checks}

    def _id(self, value):
        if not self.token:
            raise ProviderError('Set APIFY_TOKEN in .env before using Apify.')
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
            raise ProviderError('Apify: enter a task/run ID, not a URL.')
        return value

    def start_task(self, task_id, task_input, *, max_charge_usd, timeout_seconds=300):
        """Start a saved task once. Caller must persist returned run ID; never auto-retry."""
        task_id = self._id(task_id)
        if not isinstance(task_input, dict):
            raise ProviderError('Apify: task input must match the configured Actor schema.')
        if isinstance(max_charge_usd, bool) or not isinstance(max_charge_usd, (int, float)) or not math.isfinite(max_charge_usd) or max_charge_usd <= 0:
            raise ProviderError('Apify: configure a positive per-run spending cap before discovery.')
        if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, int) or not 1 <= timeout_seconds <= 3600:
            raise ProviderError('Apify: timeout must be between 1 and 3600 seconds.')
        query = urlencode({'maxTotalChargeUsd': max_charge_usd, 'timeout': timeout_seconds})
        result = self.http.request('POST', f'https://api.apify.com/v2/actor-tasks/{task_id}/runs?{query}', headers={'Authorization': f'Bearer {self.token}'}, body=task_input)
        data = result.get('data') if isinstance(result, dict) else None
        if not isinstance(data, dict) or not isinstance(data.get('id'), str) or not isinstance(data.get('status'), str):
            raise ProviderError('Apify: task start response is incomplete; inspect Runs before retrying.')
        return data

    def fetch_task_leads(self, run_id, segment):
        """Poll once, returning only a succeeded run's dataset; schedule later polls externally."""
        run_id = self._id(run_id)
        result = self.http.request('GET', f'https://api.apify.com/v2/actor-runs/{run_id}', headers={'Authorization': f'Bearer {self.token}'})
        data = result.get('data') if isinstance(result, dict) else None
        if not isinstance(data, dict) or not isinstance(data.get('status'), str):
            raise ProviderError('Apify: run status response is incomplete.')
        if data['status'] != 'SUCCEEDED':
            raise ProviderError('Apify: run has not succeeded; review its status before retrieving leads.')
        return self.fetch_leads(data.get('defaultDatasetId'), segment)
