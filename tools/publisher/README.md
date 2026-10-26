# Standalone Zernio video publisher

Node.js 22+. Install/build using `setup/setup.ps1`; it uses `npm ci` and the committed lock file. No runtime npm dependency, Studio, browser, backend or database is needed.

```powershell
node tools/publisher/dist/cli.js accounts
node tools/publisher/dist/cli.js check
node tools/publisher/dist/cli.js import --run demo-001 --video "C:\VideoWorkflow\projects\demo\edit\final.mp4"
node tools/publisher/dist/cli.js prepare --run demo-001 --metadata projects/demo/publish.json
# Review local/runs/demo-001/review.json and the video; obtain actual user authorization.
node tools/publisher/dist/cli.js publish --run demo-001 --confirm-publish
node tools/publisher/dist/cli.js inspect --run demo-001
```

`prepare` sends the MP4 to Zernio storage and calls validation; it creates no post. Avoid sharing the returned media URLs. It verifies configured account health and TikTok privacy. Each platform must belong to exactly one configured API profile; a profile may contain any requested subset. Use explicit account IDs in `local/accounts.json`:

```json
{"version":1,"profiles":{"main":{"apiKeyEnv":"ZERNIO_API_KEY","platforms":{"youtube":{"accountId":"ID_FROM_ACCOUNTS_COMMAND"}}}}}
```

For another credential, add a profile alias with its own `apiKeyEnv` entry in `local/secrets.env`. `setup/configure.ps1` prompts for `ZERNIO_API_KEY` and `ZERNIO_API_KEY_SECONDARY`; press Enter to skip the secondary key when it is not needed. For example, map the first credential's YouTube and TikTok accounts to `main`, and the second credential's Facebook and LinkedIn accounts to `secondary`:

```json
{"version":1,"profiles":{"main":{"apiKeyEnv":"ZERNIO_API_KEY","platforms":{"youtube":{"accountId":"YOUTUBE_ID"},"tiktok":{"accountId":"TIKTOK_ID"}}},"secondary":{"apiKeyEnv":"ZERNIO_API_KEY_SECONDARY","platforms":{"facebook":{"accountId":"FACEBOOK_ID"},"linkedin":{"accountId":"LINKEDIN_ID"}}}}}
```

API profile aliases in this file are kit credential groups, not necessarily the same as Zernio's brand profiles.

Metadata follows `config/publish.example.json`. Copy it into the project and edit actual values. For scheduling, add `scheduledAt` with a timezone, e.g. `2027-01-01T09:00:00+07:00`. It must be at least two minutes in the future. Scheduling is normalized to UTC; the outgoing Zernio field is `scheduledFor`. Scheduled posts are reported with `scheduledFor`, and per-profile attempts retain `scheduled` status.

The CLI returns immediately after create/status refresh. Poll using separate `inspect` calls with reasonable spacing. `status` reads only local data. `publish` cannot be repeated after attempts have been recorded, and preparation cannot erase those attempts. Checkpoints save request IDs before creating posts. A run lock prevents concurrent mutation; after a crash verify no process is active and reconcile Zernio before removing the matching `local/runs/<run>.lock`.

Use `retry --run ID --confirm-publish` for eligible recorded attempts only. Completed attempts are excluded. Partial/failed posts with a known ID use Zernio's retry endpoint. An uncertain attempt without a post ID requires human reconciliation. Once the matching post is found, `adopt --run ID --profile ALIAS --post-id ID` checks caption and account IDs before attaching it. Do not create a fresh run to evade a duplicate guard. This version deliberately does not resend uncertain POST requests or automate TikTok Inbox fallback.

The prepared plan is hashed. Changing the video, metadata or plan invalidates first publish. A plan is usable for first publish for at most 24 hours; media service constraints may require re-preparation earlier. Existing-post inspection/retry remains available afterward. Raw provider errors may contain account details; keep run files local.
