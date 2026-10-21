# Connect Attio for screening

This prototype checks whether an email already belongs to an Attio person. An exact match blocks **cold** outreach. It does not create contacts, change stages, or move your Asana pipeline. Keep the Asana suppression snapshot current until migration is confirmed.

1. Open [Attio](https://app.attio.com) and choose the workspace that will own your investor pipeline.
2. Click the dropdown beside the workspace name, then **Workspace settings**.
3. Open **Developers**, then **+ New access token**. You must be a workspace admin.
4. Name it **Kathie screening**.
5. Give it only these scopes: **Records → Read** (`record_permission:read`) and **Object configuration → Read** (`object_configuration:read`). Leave write permissions and other scopes disabled.
6. Create the token and copy it yourself.
7. Open `.env` in the main **Kathie-Shane-rev** project folder. Find `ATTIO_TOKEN=` and paste the token after the equals sign. Save. Do not paste it in chat or add it to a command.
8. Restart the local Kathie process so it reads the saved token.

The screen labels can vary; the scope identifiers in parentheses are the required permissions. [Attio token instructions](https://attio.com/help/reference/apps/generating-an-api-key), [query permissions](https://docs.attio.com/rest-api/endpoint-reference/records/list-records).

## Check the connection

Use **Capture lead** in Slack to save a draft cold contact with an email you know is already in Attio. Then choose **Check leads** and **Review all leads**. You should see an **Attio match** blocking cold outreach. This prototype saves drafts only; it does not send email. Other checks may still hold the contact until their suppression sources are complete.

Try a second draft with an email you independently confirmed is absent from Attio. Its Attio check should pass, while other screening checks still apply. An absent match means only that this exact email is absent from Attio's People object; it does not prove that the person has no other email or is unknown elsewhere.

If the app reports missing credentials, confirm `ATTIO_TOKEN` is saved and restart. HTTP 401 means check/recreate the token; 403 means check scopes and workspace access; 429 means pause and retry after the provider limit resets. Failed or malformed queries must hold screening rather than clear a lead. Never share a token or raw provider response to troubleshoot.

## Adapter contract and validation

`AttioClient(token, http=None).contains(email)` uses a read-only POST to `/v2/objects/people/records/query`. It lowercases and trims the email, uses the documented shorthand equality filter, and independently checks returned email values for an exact match. [Attio filter syntax](https://docs.attio.com/rest-api/guides/filtering-and-sorting).

A complete empty query returns false. Nonempty unrelated results, malformed email fields, oversized pages, and provider failures raise `ProviderError`. A matching record proves suppression without fetching further pages; a full page without an exact match is held, never cleared.

Validated with synthetic HTTP fixtures only. No live Attio account, token, or response was tested in this sprint.
