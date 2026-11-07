# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=1.2,<2", "google-api-python-client", "google-auth-oauthlib"]
# ///
"""Read-only MCP server for the Google AdSense Management API v2."""
import json
import os
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

SCOPES = ["https://www.googleapis.com/auth/adsense.readonly"]
CONFIG = Path(os.environ.get("ADSENSE_MCP_DIR", Path.home() / ".config/adsense-mcp"))
SECRETS = CONFIG / "client_secrets.json"
TOKEN = CONFIG / "token.json"
DEFAULT_SITE = os.environ.get("ADSENSE_DEFAULT_SITE") or None
CURRENCY = os.environ.get("ADSENSE_CURRENCY", "EUR")

mcp = FastMCP("adsense")
_service = None


def _save(creds: Credentials) -> None:
    TOKEN.write_text(creds.to_json())
    TOKEN.chmod(0o600)


def _login() -> Credentials:
    if not SECRETS.exists():
        raise SystemExit(f"Missing OAuth client file: {SECRETS}")
    flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS), SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True)
    _save(creds)
    return creds


def _creds() -> Credentials:
    creds = None
    if TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save(creds)
    if not creds or not creds.valid:
        raise RuntimeError("No valid token. Run: uv run --script server.py --auth")
    return creds


def svc():
    global _service
    if _service is None:
        _service = build("adsense", "v2", credentials=_creds(), cache_discovery=False)
    return _service


def _account(account: str | None) -> str:
    if account:
        return account if account.startswith("accounts/") else f"accounts/{account}"
    accts = svc().accounts().list().execute().get("accounts", [])
    if not accts:
        raise RuntimeError("No AdSense account is accessible with this login.")
    return accts[0]["name"]


def _rows(resp: dict) -> list[dict]:
    headers = [h["name"] for h in resp.get("headers", [])]
    return [
        {h: c.get("value") for h, c in zip(headers, r.get("cells", []))}
        for r in resp.get("rows", [])
    ]


@mcp.tool()
def list_accounts() -> list[dict]:
    """List the AdSense accounts this login can see (name, publisher id, state, time zone)."""
    return svc().accounts().list().execute().get("accounts", [])


@mcp.tool()
def list_sites(account: str | None = None) -> list[dict]:
    """List the account's sites and their approval state (READY, GETTING_READY, REQUIRES_REVIEW, NEEDS_ATTENTION)."""
    return svc().accounts().sites().list(parent=_account(account)).execute().get("sites", [])


@mcp.tool()
def list_alerts(account: str | None = None) -> list[dict]:
    """Account alerts (policy, payments, ads.txt and so on)."""
    return svc().accounts().alerts().list(parent=_account(account)).execute().get("alerts", [])


@mcp.tool()
def list_policy_issues(account: str | None = None) -> list[dict]:
    """Policy center issues, per site or page."""
    return svc().accounts().policyIssues().list(parent=_account(account)).execute().get("policyIssues", [])


@mcp.tool()
def list_payments(account: str | None = None) -> list[dict]:
    """Payments made and the current unpaid balance."""
    return svc().accounts().payments().list(parent=_account(account)).execute().get("payments", [])


@mcp.tool()
def list_ad_units(account: str | None = None) -> list[dict]:
    """Ad units across every ad client in the account."""
    acct = _account(account)
    clients = svc().accounts().adclients().list(parent=acct).execute().get("adClients", [])
    units = []
    for c in clients:
        units += svc().accounts().adclients().adunits().list(parent=c["name"]).execute().get("adUnits", [])
    return units


@mcp.tool()
def report(
    date_range: str = "LAST_30_DAYS",
    dimensions: list[str] | None = None,
    metrics: list[str] | None = None,
    site: str | None = DEFAULT_SITE,
    start_date: str | None = None,
    end_date: str | None = None,
    order_by: str | None = None,
    limit: int = 100,
    account: str | None = None,
) -> dict:
    """Run an AdSense report.

    date_range: TODAY, YESTERDAY, MONTH_TO_DATE, YEAR_TO_DATE, LAST_7_DAYS, LAST_30_DAYS or CUSTOM
      (CUSTOM needs start_date and end_date as YYYY-MM-DD).
    dimensions: e.g. DATE, MONTH, DOMAIN_NAME, URL_CHANNEL_NAME, CUSTOM_CHANNEL_NAME, AD_UNIT_NAME,
      COUNTRY_NAME, PLATFORM_TYPE_NAME, AD_FORMAT_NAME. Defaults to [DATE].
    metrics: e.g. ESTIMATED_EARNINGS, PAGE_VIEWS, PAGE_VIEWS_RPM, IMPRESSIONS, IMPRESSIONS_RPM, CLICKS,
      PAGE_VIEWS_CTR, COST_PER_CLICK, AD_REQUESTS_COVERAGE, ACTIVE_VIEW_VIEWABILITY.
      Defaults to ESTIMATED_EARNINGS, PAGE_VIEWS, PAGE_VIEWS_RPM, IMPRESSIONS, CLICKS.
    site: filter by domain (defaults to ADSENSE_DEFAULT_SITE); pass "" for the whole account.
    order_by: e.g. "-ESTIMATED_EARNINGS".
    """
    dimensions = dimensions or ["DATE"]
    metrics = metrics or ["ESTIMATED_EARNINGS", "PAGE_VIEWS", "PAGE_VIEWS_RPM", "IMPRESSIONS", "CLICKS"]
    kw = dict(
        account=_account(account),
        dateRange=date_range,
        dimensions=dimensions,
        metrics=metrics,
        limit=limit,
        currencyCode=CURRENCY,
    )
    if date_range == "CUSTOM":
        if not (start_date and end_date):
            raise ValueError("CUSTOM needs start_date and end_date (YYYY-MM-DD).")
        for p, d in (("startDate", start_date), ("endDate", end_date)):
            y, m, dd = (int(x) for x in d.split("-"))
            kw[f"{p}_year"], kw[f"{p}_month"], kw[f"{p}_day"] = y, m, dd
    if site:
        kw["filters"] = [f"DOMAIN_NAME=={site}"]
    if order_by:
        kw["orderBy"] = [order_by]
    resp = svc().accounts().reports().generate(**kw).execute()
    totals = None
    if resp.get("totals"):
        totals = _rows({"headers": resp.get("headers", []), "rows": [resp["totals"]]})[0]
    return {
        "rows": _rows(resp),
        "totals": totals,
        "warnings": resp.get("warnings"),
        "startDate": resp.get("startDate"),
        "endDate": resp.get("endDate"),
    }


if __name__ == "__main__":
    if "--auth" in sys.argv:
        _login()
        print("Token saved to", TOKEN)
        print(json.dumps(svc().accounts().list().execute(), indent=2))
    else:
        mcp.run()
