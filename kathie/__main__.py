import argparse
import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from .core import Store, SOURCES
from .jobs import JobQueue
from .providers import ApifyClient, AttioClient, HunterClient
from .service import Service

LOG = logging.getLogger(__name__)


def demo():
    """Synthetic, isolated data only: no .env or live providers are loaded."""
    from .demo import prepare_demo
    with tempfile.TemporaryDirectory(prefix='kathie-demo-') as folder:
        store, _, summary = prepare_demo(Path(folder) / 'demo.sqlite', 'DEMO')
        counts = summary['counts']
        print(f"DEMO: {counts['eligible']} eligible, {counts['blocked']} blocked, {counts['held']} held — no provider calls or outreach")
        for row in store.screen_results():
            print(f"{row['name']}: {row['status']} ({'; '.join(row['reasons']) or 'all safety checks passed'})")
        experiment = store.save_experiment(dict(name='Storage hooks', segment='tech', subject='Real estate question',
            body='Would you like me to send information?', hooks=['Exploring self-storage?', 'Considering a real estate allocation?'],
            followups=['Following up on my note. Want the information?', 'Checking back in. Interested?', 'Last note from me. Interested?'], interval_business_days=2), 'DEMO')
        preview = store.preview_experiment(experiment['id'])
        print('\nDRAFT MESSAGING TEST')
        print(json.dumps(preview, indent=2))
        from .ui import home_view
        print(f"\nSlack Home assembled: {len(home_view(store)['blocks'])} blocks. No API calls made.")


def build_runtime(owner, demo_data=False, base_dir=Path('.')):
    if demo_data:
        from .demo import prepare_demo
        path = Path(base_dir) / '.local/kathie-demo.sqlite'
        store, service, summary = prepare_demo(path, owner)
        LOG.info('DEMO active: %s. Provider responses and screening lists are fictional; no provider credits.', path)
        return store, service, path
    path = Path(os.environ.get('KATHIE_DB_PATH') or Path(base_dir) / '.local/kathie.sqlite')
    store = Store(path)
    field_map = json.loads(os.environ.get('APIFY_FIELD_MAP') or '{}')
    apify = ApifyClient(os.environ['APIFY_TOKEN'], field_map=field_map) if os.environ.get('APIFY_TOKEN') else None
    hunter = HunterClient(os.environ['HUNTER_API_KEY']) if os.environ.get('HUNTER_API_KEY') else None
    attio = AttioClient(os.environ['ATTIO_TOKEN']) if os.environ.get('ATTIO_TOKEN') else None
    return store, Service(store, owner, apify, hunter, attio.contains if attio else None), path


def run(demo_data=False):
    from dotenv import load_dotenv
    load_dotenv()
    required = ('SLACK_BOT_TOKEN', 'SLACK_APP_TOKEN', 'SLACK_OWNER_USER_ID')
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise ValueError('Populate .env before starting Slack: ' + ', '.join(missing))
    # Local relationship data and tokens stay private on creation.
    os.umask(0o077)
    owner = os.environ['SLACK_OWNER_USER_ID']
    store, service, path = build_runtime(owner, demo_data=demo_data)
    queue = JobQueue(path)
    from .slack_app import build_app
    from .ui import home_view, escape
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    app = build_app(store, queue.enqueue, owner, os.environ['SLACK_BOT_TOKEN'])
    stop = threading.Event()

    def worker():
        backoff = 1
        while not stop.is_set():
            try:
                did_work = queue.run_one(service.handle)
                for job in queue.notifications():
                    result = job['result'] or {}
                    message = result.get('message') if job['status'] == 'succeeded' else f"Task {job['status']}: {job['error']}"
                    warnings = result.get('warnings') or []
                    if warnings:
                        message += '\nNeeds review: ' + '; '.join(dict.fromkeys(warnings))
                    # Keep notification readable; complete job evidence stays local.
                    escaped = escape(message or 'Task complete.')
                    app.client.chat_postMessage(channel=owner, text=escaped[:2900])
                    app.client.views_publish(user_id=owner, view=home_view(store))
                    queue.mark_notified(job['id'])
                backoff = 1
                if not did_work:
                    stop.wait(1)
            except Exception as exc:
                code = getattr(exc, 'response', {}).get('error', '') if hasattr(getattr(exc, 'response', None), 'get') else ''
                LOG.error('Background processing/notification failed (%s %s). Jobs remain available for review.', type(exc).__name__, code)
                stop.wait(backoff)
                backoff = min(backoff * 2, 30)

    thread = threading.Thread(target=worker, name='kathie-worker', daemon=True)
    thread.start()
    try:
        SocketModeHandler(app, os.environ['SLACK_APP_TOKEN']).start()
    finally:
        stop.set()
        thread.join(timeout=2)


def main():
    parser = argparse.ArgumentParser(description='Kathie lead capture, cold screening, and draft messaging')
    parser.add_argument('command', choices=('demo', 'run'))
    parser.add_argument('--demo-data', action='store_true', help='Run Slack with fictional contacts in a separate demo database')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    if args.command == 'demo':
        demo()
    else:
        try:
            run(demo_data=args.demo_data)
        except (ValueError, json.JSONDecodeError) as exc:
            parser.error(str(exc))


if __name__ == '__main__':
    main()
