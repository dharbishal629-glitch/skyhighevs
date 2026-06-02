# Render Environment Variables — Setup Checklist

After connecting your repo to Render and creating the web service, you must manually set the following environment variables in the **Render Dashboard → Your Service → Environment** tab.

`render.yaml` marks these as `sync: false`, meaning Render intentionally leaves them blank — you must fill them in yourself before your first deploy.

---

## Required Variables

### `DATABASE_URL`
**What it is:** PostgreSQL connection string for your database.  
**Format:** `postgresql://USER:PASSWORD@HOST:PORT/DATABASE`  
**Where to get it:** Render's managed PostgreSQL dashboard (copy the "Internal Database URL" if the DB is on Render, or use your own provider's connection string).  
**Impact if missing:** The server will start but all API calls that touch the database will fail. Tables will not be created.

---

### `TOTP_SECRET`
**What it is:** A base-32 secret used to verify 6-digit TOTP (two-factor authentication) codes sent by workers when they call the API.  
**Format:** A base-32 string, e.g. `JBSWY3DPEHPK3PXP` (at least 16 characters).  
**How to generate one:**
```bash
# Node.js one-liner
node -e "const {authenticator}=require('otplib');console.log(authenticator.generateSecret())"

# Or use any TOTP secret generator (e.g. https://totp.app/generate)
```
**Impact if missing:** The `/api/tool/*` worker endpoints return `500 — Server 2FA not configured`. Workers cannot authenticate.

---

### `WORKER_API_KEY`
**What it is:** A shared API key that workers must send in the `x-api-key` header (alongside their TOTP code) to call protected tool endpoints.  
**Format:** Any hard-to-guess string, e.g. a random 32-character hex value.  
**How to generate one:**
```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```
**Impact if missing:** The `requireApiKey` middleware rejects every worker API request with `401 — Invalid API key`.

> **Note:** This variable is used in the code (`artifacts/api-server/src/middlewares/auth.ts`) but is not yet listed in `render.yaml`. Add it manually in the Render dashboard.

---

## Optional but Recommended Variables

### `ADMIN_KEY`
**What it is:** A plaintext admin password used for initial dashboard access before you set a permanent access code through the UI.  
**Format:** Any string you choose (treat it like a password).  
**When you need it:** Only on first deploy, before you log in and set a permanent admin access code via the dashboard Settings page. Once a code is stored in the database, this env var becomes a legacy fallback and can be removed.  
**Impact if missing:** On first deploy with no access code stored in the database, the server enters "setup mode" and lets anyone through — set this to lock it down immediately.

---

### `CTRL_API_URL`
**What it is:** The public URL of your deployed Render service (the app's own URL).  
**Format:** `https://your-service-name.onrender.com`  
**Why it's needed:** The server pings `${CTRL_API_URL}/api/health` every 14 minutes to prevent Render's free-tier spin-down. Workers also use it to resolve their API base URL.  
**Impact if missing:** Keep-alive pings are silently skipped (the service may spin down on Render's free tier). Worker launcher scripts may fall back to inferring the URL from request headers, which usually works but is less reliable.

---

## Already Configured (no action needed)

| Variable   | Value  | Set in `render.yaml`? |
|------------|--------|----------------------|
| `NODE_ENV` | `production` | Yes |
| `PORT`     | `10000`      | Yes — Render requires this exact port |

---

## Quick Checklist

Before your first deploy, confirm all of these are filled in on the Render dashboard:

- [ ] `DATABASE_URL` — your PostgreSQL connection string
- [ ] `TOTP_SECRET` — base-32 TOTP secret (generate one with the command above)
- [ ] `WORKER_API_KEY` — random 32-char hex key (generate one with the command above)
- [ ] `ADMIN_KEY` — a temporary admin password for first login *(remove after setting a permanent code in the dashboard)*
- [ ] `CTRL_API_URL` — set to `https://<your-service-name>.onrender.com` after your service is created

---

## How to set variables on Render

1. Open [dashboard.render.com](https://dashboard.render.com)
2. Click your web service (`skyhighevs`)
3. Go to **Environment** in the left sidebar
4. Click **Add Environment Variable** for each item above
5. Hit **Save Changes** — Render will redeploy automatically
