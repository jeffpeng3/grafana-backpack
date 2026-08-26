import json
import logging
import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from apscheduler.schedulers.background import BackgroundScheduler

GRAFANA_URL = os.environ.get("GRAFANA_URL", "").rstrip("/")
GRAFANA_API_TOKEN = os.environ.get("GRAFANA_API_TOKEN", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
TZ = os.environ.get("TZ", "Asia/Taipei")
HOUR = int(os.environ.get("BACKUP_HOUR", "9"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("backup")


def grafana_headers():
    return {"Authorization": f"Bearer {GRAFANA_API_TOKEN}"}


def github_headers():
    return {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "grafana-backpack",
    }


def fetch_dashboards(session):
    dashboards = []
    offset = 0
    limit = 1000
    while True:
        resp = session.get(
            f"{GRAFANA_URL}/api/search",
            headers=grafana_headers(),
            params={"limit": limit, "offset": offset},
            timeout=30,
        )
        resp.raise_for_status()
        page = resp.json()
        dashboards.extend(d for d in page if d.get("type") == "dash-db")
        if len(page) < limit:
            break
        offset += limit
    return dashboards


def fetch_dashboard_full(session, uid):
    resp = session.get(
        f"{GRAFANA_URL}/api/dashboards/uid/{uid}",
        headers=grafana_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["dashboard"]


def build_files(session, dashboards):
    files = {}
    for d in dashboards:
        uid = d.get("uid")
        title = d.get("title", uid)
        slug = "".join(c if (c.isalnum() or c in "-_") else "-" for c in title).strip("-")
        full = fetch_dashboard_full(session, uid)
        files[f"{slug}.json"] = {"content": json.dumps(full, indent=2, ensure_ascii=False)}
    return files


def get_gist_files(session, gist_id):
    resp = session.get(
        f"https://api.github.com/gists/{gist_id}",
        headers=github_headers(),
        timeout=30,
    )
    resp.raise_for_status()
    return {name: {"content": f["content"]} for name, f in resp.json()["files"].items()}


def upload_gist(session, files):
    description = f"Grafana dashboard backup {datetime.now(ZoneInfo(TZ)).strftime('%Y-%m-%d %H:%M')}"
    payload = {"description": description, "public": False, "files": files}
    if GITHUB_GIST_ID:
        url = f"https://api.github.com/gists/{GITHUB_GIST_ID}"
        method = session.patch
    else:
        url = "https://api.github.com/gists"
        method = session.post
    resp = method(
        url,
        headers=github_headers(),
        json=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def run_backup():
    log.info("開始備份 Grafana dashboards")
    with requests.Session() as session:
        dashboards = fetch_dashboards(session)
        log.info(f"取得 {len(dashboards)} 個 dashboard")
        if not dashboards:
            log.warning("沒有找到任何 dashboard")
            return
        files = build_files(session, dashboards)
        if GITHUB_GIST_ID:
            current = get_gist_files(session, GITHUB_GIST_ID)
            if current == files:
                log.info("無變更，跳過更新（不產生 revision）")
                return
        gist = upload_gist(session, files)
    log.info(f"備份完成，Gist: {gist['html_url']}")


GITHUB_GIST_URL = os.environ.get("GITHUB_GIST_URL", "")


def extract_gist_id(value):
    if not value:
        return ""
    match = re.search(r"([0-9a-f]{32})", value)
    if match:
        return match.group(1)
    return ""


GITHUB_GIST_ID = extract_gist_id(GITHUB_GIST_URL)
if not GITHUB_GIST_ID:
    GITHUB_GIST_ID = extract_gist_id(os.environ.get("GITHUB_GIST_ID", ""))


def main():
    scheduler = BackgroundScheduler(timezone=TZ)
    scheduler.add_job(run_backup, "cron", hour=HOUR, misfire_grace_time=86400)
    scheduler.start()
    log.info(f"排程已啟動，每天 {HOUR:02d}:00 ({TZ}) 備份")
    if GITHUB_GIST_ID:
        log.info("使用既有的 Gist")
    else:
        log.info("尚未有 Gist，首次執行會建立新的")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        scheduler.shutdown()


if __name__ == "__main__":
    main()
