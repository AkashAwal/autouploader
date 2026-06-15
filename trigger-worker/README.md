# autouploader-trigger (Cloudflare Worker)

Punctual trigger for the YouTube upload workflow. Cloudflare Cron Triggers fire
on time (11:00 and 17:00 IST) and call GitHub's `workflow_dispatch` API, which
starts a run within seconds. This is the **primary** trigger; the GitHub
workflow's own 30-minute cron stays as a **backup**. Because `main.py` tracks
which daily slots are already filled, extra triggers can never cause duplicate
uploads.

## One-time setup

### 1. Create a GitHub token
- GitHub → Settings → Developer settings → **Fine-grained personal access tokens** → Generate new token.
- **Resource owner:** your account. **Repository access:** only `AkashAwal/autouploader`.
- **Permissions → Actions: Read and write.** (That is the only permission needed.)
- Set a long expiry (or no expiry) so it does not silently lapse. Copy the token.

### 2. Deploy the Worker
From this folder:

```bash
npm install -D wrangler@latest
npx wrangler login
npx wrangler secret put GH_TOKEN   # paste the token when prompted
npx wrangler deploy
```

### 3. Verify
```bash
# Manually fire it once and confirm a run appears in GitHub Actions:
curl "https://autouploader-trigger.<your-subdomain>.workers.dev/trigger"
```
Then check the Actions tab — a `workflow_dispatch` run should start within seconds.

## Notes
- Times are UTC in `wrangler.jsonc`: `30 5` = 11:00 IST, `30 11` = 17:00 IST.
- IST has no daylight saving, so these offsets are correct year-round.
- To change repo/workflow/branch, edit the `vars` in `wrangler.jsonc` and redeploy.
- Logs: `npx wrangler tail`.
