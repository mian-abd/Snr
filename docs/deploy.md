# Hosting the demo publicly (Railway)

One container serves the built site and the API. On a public link, strangers could press Run
and spend your provider credit, so the image starts in **public mode**.

## What public mode does

Everything that only reads stays open: every GET, the exports, the decision previews
(`/learned/decisions`, `/routing/decisions`, `/learned/what-if`) and `/eligibility`.

Live provider calls (`/comparisons`, `/routes`, `/learned/routes`) are limited:

- **Daily allowances**, counted in memory and reset at 00:00 UTC. A shared allowance covers
  everyone and is the real guard. A smaller one covers each client address. `/comparisons`
  counts one call per model it sends to. A retry inside one call is not counted. If the
  chosen model fails, the router's one fallback model is a second call and needs its own
  allowance. Over a limit the answer is 429 with a plain-English message.
- **A cost ceiling per call.** The worst case is the prompt (estimated at one token per two
  characters), plus the request's maximum output tokens, with one retry, at the model's
  registry price (or its live catalog price, if higher). Above `PUBLIC_MAX_CALL_USD` the call
  is refused with 403, naming the model; the preview still shows the decision.
- Benchmark runs (`POST /benchmarks/gsm8k/runs`) are refused with 403.
- `save=true` on comparisons is ignored; nothing is written and the response says so.
- `POST /learned/catalog/refresh` runs at most once every 10 minutes; otherwise it returns
  the current status.
- `/health` reports `public_mode` and the live calls left today (`live_calls_left` shared,
  `client_live_calls_left` for the caller). The site shows them near the live-call buttons.

The limits live in one process, so run a single instance (the image does) and expect the
counts to reset when it restarts. The client address comes from `request.client.host`. Behind
Railway's proxy, `--proxy-headers` makes that the real visitor, but forwarded headers can be
spoofed, which is why the shared allowance matters more than the per-client one.

## Environment variables

Set these at run time on the host. Nothing secret is built into the image.

| Variable | Default | Meaning |
| --- | --- | --- |
| `OPENROUTER_API_KEY` | none | The only key the live features need. Without it, `/comparisons` and `/routes` answer 503, and previews still work. |
| `PUBLIC_MODE` | `true` in the image, `false` otherwise | Turns on everything above. |
| `PUBLIC_DAILY_LIVE_CALLS` | `60` | Shared live calls per UTC day. |
| `PUBLIC_CLIENT_DAILY_LIVE_CALLS` | `6` | Live calls per client address per UTC day. |
| `PUBLIC_MAX_CALL_USD` | `0.02` | Worst-case cost above which one call is refused. |
| `OPENROUTER_SITE_URL` | `http://localhost:8000` | Sent to OpenRouter as the referring site; set it to your public URL. |
| `OPENROUTER_APP_NAME` | `Adaptive LLM Router` | Sent to OpenRouter as the app name. |
| `LIVE_CATALOG_CHECK` | `true` | Compare the pool with the providers' live catalogs at startup. |
| `PORT` | `8000` | Set by Railway. |

`GEMINI_API_KEY` and `NVIDIA_API_KEY` are named in the model pool files, but the router only
offers models whose key is the OpenRouter one, so they are not needed. The OVHcloud models
need no key at all, so `/learned/routes` can still answer from them when no OpenRouter key is
set. Those calls count against the allowances too.

**Create a separate OpenRouter key for the host, with its own small credit limit** (for
example $5) in the OpenRouter dashboard. Do not reuse your everyday key. If the host is ever
abused, the most it can lose is that limit, and you can revoke the key without touching
anything else.

## Build and run the image locally

```
docker build -t adaptive-router .
docker run --rm -p 8010:8010 -e PORT=8010 adaptive-router
docker run --rm -p 8010:8010 -e PORT=8010 -e OPENROUTER_API_KEY=... adaptive-router
```

Open http://localhost:8010. With no key, previews work and live calls answer 503. Do not copy
`backend/.env` into the image: `.dockerignore` excludes it, and it should stay that way. To
check, run `docker run --rm adaptive-router sh -c 'find / -name ".env*" -not -path "/proc/*"'`;
it should print nothing.

The first build takes a couple of minutes and the image is large (scikit-learn, pyarrow,
matplotlib and litellm are part of the backend's dependencies). With no keys and no network,
the container is healthy in about two seconds: the live catalog check gives up after a few
seconds and falls back to the dated snapshot.

## Deploy to Railway

From the repo root, with the [Railway CLI](https://docs.railway.com/guides/cli) installed:

1. `railway login`
2. `railway init` for a new project, or `railway link` to use an existing one.
3. `railway up` builds the root `Dockerfile` (configured by `railway.json`) and deploys it.
   Railway waits for `/api/v1/health` to answer before it switches traffic.
4. In the Railway dashboard, open the service's **Variables** tab and add
   `OPENROUTER_API_KEY` (the separate, limited key) and `OPENROUTER_SITE_URL`. Change the
   `PUBLIC_*` limits there too if you want different ones. Saving redeploys the service.
5. `railway domain` generates a public URL (or use **Settings > Networking** in the
   dashboard). Set `OPENROUTER_SITE_URL` to it.

Check it: open the URL, then `https://<your-domain>/api/v1/health` should show
`"public_mode": true` and the calls left.

## Good to know

- The local Ollama model (Qwen 3.5 9B) shows as unavailable when hosted, because there is no
  Ollama server in the container. The router skips it and the catalog panel says why.
- The container's disk is not kept between deploys. Public mode writes nothing that matters.
