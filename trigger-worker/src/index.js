/**
 * Punctual trigger for the autouploader GitHub Actions workflow.
 *
 * Cloudflare Cron Triggers fire on time and call GitHub's workflow_dispatch
 * API, which starts a run within seconds. This replaces GitHub's own
 * `schedule:` cron as the primary trigger, because GitHub-scheduled runs are
 * best-effort and are frequently delayed or dropped at the top of the hour.
 *
 * The GitHub workflow keeps its own 30-minute cron as a backup, and main.py's
 * per-slot bookkeeping means an extra trigger can never cause a double upload.
 */

async function dispatchWorkflow(env, cron) {
  const url = `https://api.github.com/repos/${env.GH_REPO}/actions/workflows/${env.GH_WORKFLOW}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "autouploader-trigger",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: env.GH_REF || "main" }),
  });

  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`GitHub dispatch failed (${res.status}) for cron "${cron}": ${detail}`);
  }
  console.log(`Dispatched ${env.GH_WORKFLOW} on ${env.GH_REF} (cron "${cron}").`);
}

export default {
  // Fired by Cloudflare Cron Triggers at the scheduled UTC times.
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatchWorkflow(env, event.cron));
  },

  // Manual trigger for testing: GET /trigger?key=<GH_TOKEN-not-needed> simply
  // calls the same dispatch. Visiting the root returns a status line.
  async fetch(request, env, ctx) {
    const { pathname } = new URL(request.url);
    if (pathname === "/trigger") {
      try {
        await dispatchWorkflow(env, "manual");
        return new Response("Dispatched.\n", { status: 200 });
      } catch (err) {
        return new Response(`Error: ${err.message}\n`, { status: 502 });
      }
    }
    return new Response(
      "autouploader-trigger is running. Cron fires workflow_dispatch at 05:30 & 11:30 UTC.\n",
      { status: 200 },
    );
  },
};
