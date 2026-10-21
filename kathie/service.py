"""Job orchestration for capture and drafts. There is no sending adapter."""
import logging

from .providers import ProviderError

LOG = logging.getLogger(__name__)


class Service:
    def __init__(self, store, owner, apify=None, hunter=None, attio_lookup=None):
        self.store = store
        self.owner = owner
        self.apify = apify
        self.hunter = hunter
        self.attio_lookup = attio_lookup

    def enrich(self, lead_id):
        lead = self.store.get_lead(lead_id)
        if lead['email']:
            return []
        if self.hunter is None:
            return ['Email is missing. Add it manually or configure Hunter and capture this contact again.']
        try:
            found = self.hunter.find_email(lead)
            if not found['email']:
                return ['Hunter did not find an email. Add a known address before screening.']
            self.store.set_email(lead_id, found['email'])
            self.store.set_verification(lead_id, found['status'])
            return [] if found['status'] == 'valid' else ['Found email needs verification before cold outreach.']
        except (ProviderError, ValueError) as exc:
            warning = str(exc)
            LOG.warning('Email acquisition incomplete: %s', warning)
            return [warning]

    def handle(self, kind, payload):
        if not self.owner or payload.get('user_id') != self.owner:
            raise PermissionError('Only the configured owner can run this job.')
        if kind == 'capture':
            lead_id = self.store.add_lead(payload['lead'])
            supplied_email = payload['lead'].get('email')
            if supplied_email and not self.store.get_lead(lead_id)['email']:
                self.store.set_email(lead_id, supplied_email)
            warnings = self.enrich(lead_id)
            lead = self.store.get_lead(lead_id)
            track = {'warm': 'Warm follow-up', 'ambient': 'Ambient follow-up', 'cold': 'Cold outreach candidate'}[lead['relationship']]
            return {'lead_id': lead_id, 'warnings': warnings,
                'message': f'{track} saved. Run cold screening to review eligibility. Automated sending comes in the next milestone.'}
        if kind == 'import':
            if self.apify is None:
                raise ProviderError('Set APIFY_TOKEN in .env before importing leads.')
            leads = self.apify.fetch_leads(payload['dataset_id'], payload['segment'])
            imported, warnings = [], []
            for lead in leads:
                lead_id = self.store.add_lead(lead)
                if lead.get('email') and not self.store.get_lead(lead_id)['email']:
                    self.store.set_email(lead_id, lead['email'])
                imported.append(lead_id)
                warnings.extend(self.enrich(lead_id))
            return {'lead_ids': sorted(set(imported)), 'warnings': warnings,
                'message': f'Imported {len(set(imported))} contacts from {len(leads)} rows. Run cold screening before preparing a campaign.'}
        if kind == 'snapshot':
            self.store.save_snapshot(payload['source'], payload['emails'], payload['complete'])
            return {'message': f"Saved the complete {payload['source']} list ({len(set(payload['emails']))} addresses). Run screening again to apply it."}
        if kind == 'screen':
            warnings = []
            for lead in self.store.list_leads():
                if not lead['email']:
                    warnings.extend(self.enrich(lead['id']))
            results = self.store.screen_leads(attio_lookup=self.attio_lookup,
                verifier=self.hunter.verify if self.hunter else None)
            counts = {state: sum(row['status'] == state for row in results) for state in ('eligible', 'blocked', 'held')}
            return {'counts': counts, 'warnings': warnings,
                'message': f"Cold screening: {counts['eligible']} ready for review, {counts['blocked']} blocked from cold outreach, {counts['held']} held. Warm contacts use a separate follow-up track."}
        if kind == 'experiment':
            experiment = self.store.save_experiment(payload['data'], payload['user_id'], payload.get('experiment_id'))
            return {'experiment_id': experiment['id'], 'version': experiment['version'],
                'message': f"Saved draft messaging test, version {experiment['version']}. Open Home to edit or preview the complete sequence. Nothing sends yet."}
        raise ValueError('Unknown job type.')
