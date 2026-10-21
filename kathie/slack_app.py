"""Owner-only Socket Mode callbacks; no provider requests in UI callbacks."""
import logging
import sys
import re
from .ui import form, extract, parse_submission, home_view, preview_blocks, section, result_text, results_view
log=logging.getLogger(__name__)

def build_app(store, enqueue, owner_user_id, bot_token, home_publisher=None, app_factory=None):
    if not owner_user_id: raise ValueError('Set SLACK_OWNER_USER_ID before starting Kathie.')
    if app_factory is None:
        from slack_bolt import App
        app_factory=App
    app=app_factory(token=bot_token,token_verification_enabled=False)
    def allowed(body): return (body.get('user',{}).get('id') if isinstance(body.get('user'),dict) else body.get('user_id'))==owner_user_id
    def publish(client):
        view=home_view(store)
        if home_publisher: home_publisher(owner_user_id,view)
        else: client.views_publish(user_id=owner_user_id,view=view)
    def safe_error(client=None):
        exc=sys.exc_info()[1]
        classification=type(exc).__name__ if exc else 'UnknownError'
        code=None
        if classification=='SlackApiError':
            try: code=exc.response['error']
            except (KeyError,TypeError,AttributeError): pass
        if not isinstance(code,str) or not re.fullmatch(r'[a-z_]{1,80}',code): code=None
        log.error('Slack operation failed (%s%s)',classification,': '+code if code else '',exc_info=False)
        message='This action failed. Check the local application log and try again.'
        if client is not None:
            try: client.chat_postMessage(channel=owner_user_id,text=message)
            except Exception: log.error('Could not deliver the failure notice to Shane',exc_info=False)
        return message
    @app.event('app_home_opened')
    def home(event,client):
        if event.get('user')!=owner_user_id: return
        try: publish(client)
        except Exception: safe_error(client)
    @app.command('/kathie')
    def command(ack,body,respond,client):
        ack()
        if not allowed(body): respond('Only Shane can use Kathie.'); return
        args=body.get('text','').strip().split(); action=args[0] if args else 'home'
        try:
            kind={'suppressions':'snapshot'}.get(action,action)
            if kind in ['capture','import','snapshot','experiment']:
                existing=store.get_experiment(args[1]) if kind=='experiment' and len(args)>1 else None
                client.views_open(trigger_id=body['trigger_id'],view=form(kind,existing))
            elif action=='screen':
                enqueue('screen',{'user_id':owner_user_id},'screen:'+body['trigger_id']); respond('Screening queued. I’ll report the result when it finishes.')
            elif action=='results':
                client.views_open(trigger_id=body['trigger_id'],view=results_view(store.screen_results()))
            elif action=='home': publish(client); respond('Open Kathie’s Home tab to review your leads and drafts.')
            else: respond('Use /kathie home, capture, import, suppressions, screen, results, or experiment. To edit: /kathie experiment followed by its saved ID.')
        except Exception: respond(safe_error())
    for kind in ['capture','import','snapshot','experiment']:
        def register(kind):
            @app.action('kathie_'+kind)
            def open_form(ack,body,client):
                ack()
                if not allowed(body): return
                try: client.views_open(trigger_id=body['trigger_id'],view=form(kind))
                except Exception: safe_error(client)
            @app.view('kathie_'+kind)
            def submit(ack,body,view):
                if not allowed(body): ack(response_action='errors',errors={view['blocks'][0]['block_id']:'Only Shane can use Kathie.'}); return
                try: payload=parse_submission(kind,extract(view))
                except ValueError as exc:
                    ack(response_action='errors',errors={view['blocks'][0]['block_id']:str(exc)}); return
                payload['user_id']=owner_user_id
                if kind=='experiment': payload['experiment_id']=view.get('private_metadata') or None
                try:
                    enqueue(kind,payload,'view:'+view['id']+':'+view.get('hash',''))
                except Exception:
                    ack(response_action='errors',errors={view['blocks'][0]['block_id']:safe_error()}); return
                ack()
        register(kind)
    @app.action('kathie_screen')
    def screen(ack,body,client):
        ack()
        if not allowed(body): return
        try:
            enqueue('screen',{'user_id':owner_user_id},'screen:'+body['trigger_id'])
            client.chat_postMessage(channel=owner_user_id,text='Screening queued. I’ll report the result when it finishes.')
        except Exception: safe_error(client)
    @app.action('kathie_results')
    def results(ack,body,client):
        ack()
        if not allowed(body): return
        try: client.views_open(trigger_id=body['trigger_id'],view=results_view(store.screen_results()))
        except Exception: safe_error(client)
    for direction in ['next','previous']:
        def register_results_page(direction):
            @app.action('kathie_results_'+direction)
            def results_page(ack,body,client):
                ack()
                if not allowed(body): return
                try: client.views_update(view_id=body['view']['id'],hash=body['view'].get('hash'),view=results_view(store.screen_results(),int(body['actions'][0]['value'])))
                except Exception: safe_error(client)
        register_results_page(direction)
    @app.action('kathie_edit')
    def edit(ack,body,client):
        ack()
        if not allowed(body): return
        try: client.views_open(trigger_id=body['trigger_id'],view=form('experiment',store.get_experiment(body['actions'][0]['value'])))
        except Exception: safe_error(client)
    @app.action('kathie_preview')
    def preview(ack,body,client):
        ack()
        if not allowed(body): return
        try:
            identifier=body['actions'][0]['value']; blocks=preview_blocks(store.preview_experiment(identifier))
            client.views_open(trigger_id=body['trigger_id'],view=preview_view(identifier,blocks,0))
        except Exception: safe_error(client)
    def preview_view(identifier,blocks,page):
        total=(len(blocks)+89)//90; content=blocks[page*90:(page+1)*90]
        if page+1<total: content=content+[{'type':'actions','elements':[{'type':'button','text':{'type':'plain_text','text':'Next page'},'action_id':'kathie_preview_next','value':f'{identifier}|{page+1}'}]}]
        return {'type':'modal','title':{'type':'plain_text','text':f'Draft preview {page+1}/{total}'},'close':{'type':'plain_text','text':'Close'},'blocks':content}
    @app.action('kathie_preview_next')
    def next_page(ack,body,client):
        ack()
        if not allowed(body): return
        try:
            identifier,page=body['actions'][0]['value'].rsplit('|',1)
            client.views_update(view_id=body['view']['id'],hash=body['view'].get('hash'),view=preview_view(identifier,preview_blocks(store.preview_experiment(identifier)),int(page)))
        except Exception: safe_error(client)
    return app
