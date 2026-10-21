# Connect Apify

1. Sign into https://console.apify.com/ . Open Settings → Integrations and create/copy a personal API token. Put it after `APIFY_TOKEN=` in the project `.env`. Do not paste it into chat.
2. For the prototype, open a COMPLETED Actor run. Open its Dataset and copy the dataset ID. In Slack use `/kathie import`, enter that ID, and choose Tech or Real estate/construction.
3. Dataset rows need at least a name, LinkedIn URL, or email. Default mappings accept firstName, lastName, email, companyWebsite, linkedinUrl, id, headline, and their documented snake-case alternatives. Actor-specific nested paths can be passed as `field_map` to ApifyClient. A segment label alone never verifies audience eligibility.
4. Review imported leads. An empty email needs Hunter acquisition. A mapped company website/domain plus first and last names enables acquisition; source Actors must supply those fields for that flow.

## Audience evidence

Tech requires LA metro/Bay Area location, tech-company employment (any role), UCLA/UC Berkeley attendance, and like/comment/repost engagement on relevant real estate/storage/tax content. Real estate/construction requires profession and location only.

Source rows may carry `audience: {checks: {location: true, tech_employment: true, school: true, engagement: true}}` (real estate uses `real_estate_or_construction`). Only populate true/false when source evidence supports it. Store the original dataset for audit. Absent checks stay Unverified and list missing fields; false checks are Excluded. Audience uncertainty does not substitute for suppression screening, which can still hold the lead.

## Automatic relevant-post discovery: configuration still needed

The requested chain is keyword post search → people who liked/commented/reposted → profile/company/education enrichment → audience evidence → email acquisition. No production chain or Slack discovery action is connected yet. Import works now; it does not automatically discover posts.

An Apify Store Actor that supports post searches and engagement/profile extraction is a candidate: https://apify.com/scrapeforge/linkedin-all-in-one . A separate keyword search Actor is https://apify.com/automly/linkedin-post-search-scraper . Actor listings are vendor claims; neither has been live-tested here. Choose Actors after reviewing their input/output schemas, pricing, account requirements, and a sample output. Do not infer a person's qualifying engagement from a post's aggregate reaction count.

Create saved Tasks with explicit supported inputs. Post-search keywords should cover self storage, real estate investment, and tax optimization. Each follow-on stage must use actual post/profile IDs from the previous output. The adapter can start a configured task with `start_task(task_id, task_input, max_charge_usd=..., timeout_seconds=...)`. Persist the returned run ID immediately. Poll with `fetch_task_leads(run_id, segment)` only once the task's OUTPUT IS LEAD ROWS. Post datasets cannot be imported as people; field mapping and the multi-stage orchestration still need implementation.

A positive per-run charge cap and timeout are required. `maxTotalChargeUsd` is an Apify run option; charging semantics depend on the Actor's pricing model. Verify support and account billing before a real run. A network timeout may occur after a run starts: inspect Runs before retrying, so you do not incur duplicate charges.

## Validation

Eight offline fixture tests exercise pagination, audience checks, task budgeting, start/status retrieval, and pending-run holds. No paid scraping or credentialed request was run.

Official references: https://docs.apify.com/api/v2/actor-task-runs-post , https://docs.apify.com/api/v2/actor-run-get , https://docs.apify.com/api/v2/dataset-items-get .
