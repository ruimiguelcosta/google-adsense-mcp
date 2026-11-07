# Google AdSense MCP

A small, read-only MCP server that lets Claude (or any MCP client) look at your Google AdSense account: earnings, page views, RPM, sites, alerts, policy issues and payments.

I wanted to ask things like "how did goaway.pt do this month compared to last?" without opening the AdSense dashboard, and I couldn't find an AdSense MCP I trusted with my account. So this is a single Python file built on the official AdSense Management API v2. It only ever asks for the `adsense.readonly` scope, so it can read your numbers but can't change anything.

## What you get

| Tool | What it does |
| --- | --- |
| `list_accounts` | Lists the AdSense accounts your Google login can see. |
| `list_sites` | Shows each site and whether it's approved (`READY`, `GETTING_READY`, `REQUIRES_REVIEW`, `NEEDS_ATTENTION`). |
| `list_alerts` | Shows account alerts, such as ads.txt problems, payment holds and policy warnings. |
| `list_policy_issues` | Shows Policy Center issues per site or page. |
| `list_payments` | Lists past payments and your current unpaid balance. |
| `list_ad_units` | Lists every ad unit across your ad clients. |
| `report` | Runs a report with any dimensions and metrics, optionally filtered to one domain. |

`report` defaults to the last 30 days, broken down by date, with earnings, page views, page RPM, impressions and clicks. You can ask for anything else the API supports: by country, by ad unit, by platform, a custom date range, sorted by earnings, and so on.

## What you need

- [uv](https://docs.astral.sh/uv/). It installs the Python dependencies on the first run, so there's no virtualenv to manage.
- A Google account with access to the AdSense account you want to read.
- A Google Cloud project where you can enable an API and create an OAuth client. It's free and takes about five minutes.

## Setup

### 1. Create the Google Cloud project

1. Go to https://console.cloud.google.com/projectcreate and create a project (I called mine `adsense-mcp`).
2. Open **APIs & Services → Library**, search for **AdSense Management API** and click **Enable**.

Use the same Google account that owns the AdSense account. If the project belongs to a different account, the API calls will fail with `SERVICE_DISABLED` or `PERMISSION_DENIED`, even when the login itself works.

### 2. Set up the OAuth consent screen

In **Google Auth Platform → Overview → Get started**:

- **App name:** anything you like, e.g. "AdSense MCP".
- **Audience:**
  - **Internal** if you're on Google Workspace and the AdSense account is in the same organisation. There's no verification, and tokens don't expire after a week.
  - **External** for a personal Gmail account. Then add yourself under **Audience → Test users**. Be aware that refresh tokens for apps in "Testing" mode expire after 7 days, so you'll need to run `--auth` again weekly unless you publish the app.
- **Contact email:** your own address.

### 3. Create the OAuth client

1. Go to **Google Auth Platform → Clients → Create client**.
2. Choose **Desktop app** as the application type and give it a name.
3. Download the JSON file and save it as:

```
~/.config/adsense-mcp/client_secrets.json
```

```bash
mkdir -p ~/.config/adsense-mcp
mv ~/Downloads/client_secret_*.json ~/.config/adsense-mcp/client_secrets.json
chmod 600 ~/.config/adsense-mcp/client_secrets.json
```

### 4. Log in once

```bash
git clone git@github.com:ruimiguelcosta/google-adsense-mcp.git
cd google-adsense-mcp
uv run --script server.py --auth
```

Your browser opens and asks you to sign in and allow read-only access to AdSense. Once you approve, the token is saved to `~/.config/adsense-mcp/token.json` and the script prints the accounts it can see. If it prints your publisher account (`accounts/pub-…`), you're done.

The token refreshes on its own after that. If you ever change OAuth client, or want to log in with another account, just run `--auth` again.

### 5. Add it to Claude Code

Put a `.mcp.json` in the folder you run Claude Code from (or merge this into the one you already have):

```json
{
  "mcpServers": {
    "adsense": {
      "type": "stdio",
      "command": "uv",
      "args": ["run", "--script", "/absolute/path/to/google-adsense-mcp/server.py"],
      "env": {
        "ADSENSE_DEFAULT_SITE": "example.com",
        "ADSENSE_CURRENCY": "EUR"
      }
    }
  }
}
```

Or register it from the terminal:

```bash
claude mcp add adsense --scope user \
  -e ADSENSE_DEFAULT_SITE=example.com \
  -- uv run --script /absolute/path/to/google-adsense-mcp/server.py
```

Restart Claude Code and approve the `adsense` server when it asks. If `uv` isn't on the PATH Claude Code sees, use its full path, e.g. `/Users/you/.local/bin/uv`.

Claude Desktop works the same way: add the same `adsense` block to `claude_desktop_config.json`.

## Configuration

Everything is optional and set through environment variables:

| Variable | Default | What it's for |
| --- | --- | --- |
| `ADSENSE_DEFAULT_SITE` | *(none)* | Domain that `report` filters on when you don't name one. Leave it empty to report on the whole account. |
| `ADSENSE_CURRENCY` | `EUR` | Currency used for earnings in reports. |
| `ADSENSE_MCP_DIR` | `~/.config/adsense-mcp` | Where `client_secrets.json` and `token.json` live. |

## Things to ask

Once it's connected, you can just talk to it:

- "How much did goaway.pt earn in the last 7 days?"
- "Show me RPM by country for this month, highest first."
- "Compare October and September earnings for the whole account."
- "Are there any AdSense alerts or policy issues I should know about?"
- "Is my new site approved yet?"
- "What's my unpaid balance?"

## Troubleshooting

**`SERVICE_DISABLED` / "AdSense Management API has not been used in project …"**
The API isn't enabled in the project that owns your OAuth client. Enable it (step 1) and wait a couple of minutes. Check that you're looking at the right project: the number in the error is the project number.

**"You need additional access to the project" in the Cloud console**
You're signed in to the console with a different Google account from the one that created the project. Switch accounts, or create a new project with the account you're using.

**`No valid token. Run: uv run --script server.py --auth`**
There's no token yet, or the refresh token was revoked or expired. Run `--auth` again.

**`access_denied` or "app not verified" during login**
On an External app in testing mode, your account has to be on the **Test users** list.

**Earnings look slightly off compared to the dashboard**
The API returns *estimated* earnings, just like the dashboard. Today's and yesterday's figures keep changing for a while, and finalised numbers show up at the start of the next month.

**`ModuleNotFoundError: No module named 'mcp.server.fastmcp'`**
You've ended up on version 2 of the MCP Python SDK. The script pins `mcp<2` in its inline metadata, so run it with `uv run --script` rather than plain `python`.

## Security notes

- The only scope requested is `https://www.googleapis.com/auth/adsense.readonly`.
- `client_secrets.json` and `token.json` stay on your machine with `600` permissions. They're ignored by git and should never be committed.
- To revoke access, remove the app at https://myaccount.google.com/permissions and delete `~/.config/adsense-mcp/token.json`.

## License

MIT
