"""Verify all Grafana dashboard panels return data via the plugin system."""

import json
import urllib.request

# Fetch dashboard definition from Grafana
req = urllib.request.Request(
    "http://localhost:3000/api/dashboards/uid/asset_dashboard_main",
    headers={"Authorization": "Basic YWRtaW46YWRtaW4="},  # admin:admin
)
resp = urllib.request.urlopen(req, timeout=10)
dash = json.loads(resp.read())["dashboard"]

panels = dash["panels"]
data_panels = [p for p in panels if p["type"] != "row"]

print(f"Dashboard: {dash['title']}")
print(f"Total panels: {len(panels)}  (data: {len(data_panels)}, rows: {len(panels) - len(data_panels)})")
print(f"Tags: {dash.get('tags', [])}")
print()

ok_count = 0
fail_count = 0

for p in data_panels:
    targets = p.get("targets", [])
    if not targets:
        continue
    url = targets[0].get("url", "").replace("http://api:8000", "http://localhost:8000")
    if not url:
        continue
    try:
        r = urllib.request.urlopen(url, timeout=5)
        data = json.loads(r.read())
        if "items" in data:
            count = len(data["items"])
        elif "plugins" in data:
            count = data["total"]
        elif "total" in data:
            count = data["total"]
        else:
            count = "?"
        status = "OK"
        ok_count += 1
    except Exception as e:
        count = 0
        status = f"FAIL ({e})"
        fail_count += 1

    print(f"  [{status:4s}] Panel {p['id']:2d} [{p['type']:12s}] {p['title']:30s}  data={count}")

print(f"\nResult: {ok_count} passed, {fail_count} failed out of {len(data_panels)} data panels")

# Also verify /api/v1/plugins
r2 = urllib.request.urlopen("http://localhost:8000/api/v1/plugins", timeout=5)
plugins = json.loads(r2.read())
print(f"\nLoaded plugins ({plugins['total']}):")
for pl in plugins["plugins"]:
    print(f"  - {pl['key']:10s}  {pl['name']:20s}  v{pl['version']}  provider={pl['provider_key']}")
