# Kathie RevOps

Slack-based lead capture, cold-outreach screening, and editable messaging tests for the fund raising.

This first release saves contacts and drafts. Campaign creation, live email sending, automated follow-ups, reply ingestion, and outreach reports are the next milestone. Meetings, decks, investor-portal steps, and funding remain manual.

## Try it without accounts

Install [uv](https://docs.astral.sh/uv/), then run from this project folder:

```sh
uv sync --locked --python 3.12
uv run --frozen -m kathie demo
uv run --frozen -m unittest discover -s tests -v
```

The offline demo uses nine fictional contacts in a temporary database. It exercises actual acquisition and screening adapters with simulated responses: 2 eligible, 5 blocked, and 2 held. It makes no provider or Slack calls. Sequence previews show follow-ups at business-day offsets 2, 4, and 6.

## Try the fictional batch in Slack

Stop the normal app process with Ctrl+C, then start only one process:

```sh
uv run --frozen -m kathie run --demo-data
```

Reopen Kathie's Home tab. The first block must say DEMO. Nine contacts should show 2 eligible, 5 blocked, and 2 held. Review all leads explains each outcome: valid acquired address; Attio match; Asana match; catch-all address; missing email; Warm track; Ambient track; known audience mismatch; unverified school with otherwise clear checks.

Demo mode uses `.local/kathie-demo.sqlite`, ignores real provider credentials and KATHIE_DB_PATH, and never modifies `.local/kathie.sqlite`. Slack itself uses your existing connection tokens. All source and provider responses are simulated, so no Apify/Hunter credits are consumed. Synthetic complete screening lists exist only in the demo database. Real missing lists continue to hold real leads.

Try Import leads with dataset ID `demo` and Tech audience, run Check leads, review reasons, and save/edit/preview a named messaging test. Try adding an opt-out for `acquired@example.com`; Alex should become blocked when screened again. Your demo edits persist across restart. A new fictional identity outside the fixtures will be held because its simulated provider checks are unknown.

To return to real data, stop the demo process with Ctrl+C and run `uv run --frozen -m kathie run`. Reopen Home and confirm the DEMO banner is gone. Run only one process per Slack app to avoid competing callbacks.

Real lead datasets and internal working notes remain local and are excluded from version control. The included demo uses fictional contacts.

## Connect Slack

1. Create a Slack app **from a manifest** at [Slack Apps](https://api.slack.com/apps), using `slack-manifest.json`.
2. Install it into your workspace. Copy its bot token into `SLACK_BOT_TOKEN` in `.env`.
3. Under Basic Information, create an app-level token with `connections:write`. Put it in `SLACK_APP_TOKEN`.
4. In Slack, open your profile, select the menu, and copy your member ID. Put it in `SLACK_OWNER_USER_ID`. Only this person can operate the app.
5. If `.env` does not exist, copy `.env.example` to `.env`. Enter optional provider tokens there; never paste tokens into chat. `.env` and `.env.local` are ignored by Git.
6. Start the app:

```sh
uv run --frozen -m kathie run
```

Open Kathie's Home tab or type `/kathie`. Socket Mode needs an outbound connection and a running process; it does not need a public webhook URL. The prototype runs one local worker. Keep only one app process running against a database.

| Action | Slack interface |
|---|---|
| Save a contact | Capture lead or `/kathie capture` |
| Import a researched batch | Import leads or `/kathie import` |
| Supply existing-contact lists | Screening lists or `/kathie suppressions` |
| Check cold eligibility | Check leads or `/kathie screen` |
| Review every result | Review all leads or `/kathie results` |
| Write a messaging test | Draft messaging or `/kathie experiment` |
| Edit or preview a saved test | Buttons on Home; `/kathie experiment ID` also edits |

Background tasks acknowledge immediately. Their results arrive in a Slack DM and refresh Home. Failed and interrupted tasks remain recorded; they do not automatically repeat credit-consuming provider calls. Check results before resubmitting interrupted work.

## Capture and relationships

Save name, email, optional phone/profile, source, audience, and relationship notes. Hunter now supports first/last name with company domain, company/full-name, or a LinkedIn profile alone. Actual account access and coverage remain unverified.

- **Warm:** you know the person personally.
- **Ambient:** you have met, but do not know the person personally. A short “Where we met” note is required before outreach, and the first message must refer to that meeting. Capture can remain incomplete in this draft-only prototype; enrollment enforcement belongs to the next sending milestone.
- **Cold:** you have never met.

Only cold contacts can pass cold screening. Warm and Ambient contacts are saved for separate automated follow-up tracks in the next milestone. Their presence in Attio/Asana will not by itself forbid normal follow-up in those tracks.

Duplicate captures preserve original context and the strongest relationship: Warm, then Ambient, then Cold. A duplicate cannot quietly turn a known contact into a cold lead. If an existing profile lacks an email, capturing that profile again with a known address fills it. Different addresses for one person and deliberate relationship downgrades need a future reconciliation interface; this prototype stores one primary email per contact.

## Screening

Cold screening checks Attio, Asana, beehiiv, MailerLite, reply history, prior sends, opt-outs, hard bounces, and email verification. Positive matches block cold outreach. Missing, incomplete, failed, or expired checks hold the lead. A valid email verification alone never clears someone for outreach.

Until live integrations replace snapshots, paste complete email lists through Screening lists. Empty lists must be explicitly confirmed complete. Snapshots and screening evidence expire after 24 hours. Refresh them and recheck before preparing a campaign. Historical replies, sends, opt-outs, and bounces remain suppressed after later list replacement.

`ATTIO_TOKEN` enables a read-only exact-email lookup; otherwise provide a complete Attio snapshot. Do not insert new cold prospects into Attio before screening: the conservative prototype policy blocks any existing Attio contact. Asana remains required during migration. This is an email-based check, not a full person/alias matching engine.

## Providers

- `APIFY_TOKEN`: imports an already completed dataset, paginating every row before capture. Actor execution and choosing a LinkedIn actor are later work.
- `HUNTER_API_KEY`: finds emails from first name, last name, and company domain, and verifies known addresses. Catch-all, unknown, and other risky outcomes do not pass verification.
- `ATTIO_TOKEN`: read-only person query. No CRM writes yet.

Connection guides: [Apify](APIFY-SETUP.md), [Hunter](HUNTER-SETUP.md), [Attio](ATTIO-SETUP.md). Slack is connected and its Home/capture/draft views were verified live. The three provider adapters passed fixture tests; their live accounts are still unverified.

Apify has bounded saved-task start/status APIs, but automatic post → engagement → profile discovery is not wired to the app yet. It requires selected Actors, validated stage schemas, explicit spending caps, and orchestration. Completed lead-dataset import works now.

Audience checks are separate from safety screening. Tech criteria: tech-company employment, LA metro/Bay Area, UCLA/UC Berkeley attendance, and relevant real estate/storage/tax LinkedIn engagement. Real estate/construction criteria: profession and the same location. Known false checks exclude a lead; missing checks display Unverified with missing details and do not themselves create a safety hold. Source rows must carry evidence; merely selecting an audience does not verify it.

Apify actors have different schemas. Defaults recognize `firstName`/`first_name`, `lastName`/`last_name`, `email`/`emailAddress`, `companyWebsite`/`domain`/`companyDomain`, and `linkedinUrl`/`profileUrl`/`profile_url`. If your actor differs, set `APIFY_FIELD_MAP` in `.env` to a JSON object such as `{"first_name":"person.firstName","email":"contact.email"}`. Invalid rows fail visibly. Imports over 100 pages must be split.

Missing provider credentials do not create false clearance. Provider failures appear as held checks, task failures, or acquisition warnings. These adapters have been verified with fixtures; actual account credentials and live calls have not been tested.

## Messaging tests

Create a named test for one segment, with subject, shared body, 2–5 opening lines, and a finite ordered follow-up list. New tests contain editable starter copy with three openings and three follow-ups. Enter one opening per line. Separate follow-ups with a line containing `---`. Each follow-up is two business days after the preceding message. Copy containing em dashes is rejected under the outreach rules.

Editing creates a new immutable version. Preview shows every opening/body combination and every follow-up. Slack inputs allow 3,000 characters per field, including the combined follow-up field; the stored core has no arbitrary follow-up count limit. Complete previews paginate rather than silently truncating saved copy. Suppression-list paste also has a 3,000-character limit; larger-list import is future work, and a partial list must never be attested complete.

The app does not yet assign leads to variants, approve sending, compute calendar send dates, or classify replies. Confirmed scheduling requirements: Pacific time, weekdays excluding U.S. federal holidays, cutoff November13 2026, send time set by Shane and included in approval. These must be implemented before sending. CPA review of tax hooks remains required.

Discovery returns the supplied leads for Shane's defined segments. It does not add an investor suitability score or substitute a software judgment for Shane's decision about Osage investor fit.

## Local data and development

Data lives in `.local/kathie.sqlite` by default; override `KATHIE_DB_PATH` in `.env`. It includes contacts, screening history, immutable drafts, and durable jobs. The app creates private local files; do not share the database or `.env`.

This project folder is the Git checkout. Earlier temporary build worktrees no longer exist. Secrets, local databases, real lead datasets, and internal working notes are excluded by `.gitignore`.

## How this was built

This project was developed with AI assistance using OpenAI Codex. Automated tests cover simulated provider responses; they do not establish live provider access or authorize outreach.

Primary API references: [Slack Socket Mode](https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/), [Apify API](https://docs.apify.com/api/v2), [Hunter API](https://hunter.io/api-documentation/v2.md), [Attio query API](https://docs.attio.com/rest-api/endpoint-reference/records/list-records).
