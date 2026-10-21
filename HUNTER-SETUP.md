# Connect Hunter

1. Sign into [Hunter](https://hunter.io/) and open the dashboard's API section.
2. Create or copy your API key. In this project's gitignored `.env`, enter it after `HUNTER_API_KEY=` and save. Do not paste it into chat or terminal commands.
3. Tell the orchestrator that Hunter is configured. The orchestrator can run one explicitly approved live lookup against a known contact through the app. That lookup may consume account credits.
4. Review the result in Slack. Only `valid` counts as verified. Catch-all, disposable, webmail, pending, missing results, and unknown remain uncertain. Failed requests hold the lead.

The adapter accepts first and last name plus company domain; company name plus full name; or a LinkedIn profile URL/handle on its own. Work email coverage varies by person and Hunter account entitlement. An acquired email still needs every suppression check; acquisition never enrolls a contact.

Requests use a Bearer header so the key does not enter a URL. HTTP failures, quota errors, malformed responses, and non-200 responses (including incomplete 202 results) surface as safe ProviderError messages. This prototype does not poll pending jobs automatically.

Validation in this sprint uses 11 fake-HTTP tests only. No credentials were read and no live Hunter requests were made. Passing fixtures proves adapter behavior, not real account access or email coverage. Hunter's public `test-api-key` returns dummy data and also cannot prove live coverage.

Official references: [API reference](https://hunter.io/api-documentation/v2.md), [API key and dummy test behavior](https://help.hunter.io/en/articles/12149400-hunter-api-for-data-plans).
