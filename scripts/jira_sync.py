"""Create the project backlog in Jira Cloud through the official REST API.

Reads docs/jira-backlog.csv and creates Epics, Stories, Tasks and Sub-tasks with
their parent links, labels, priorities, story points, assignees (when a Jira
user with the same display name exists) and status.

Settings come from .env (never commit real values):
    JIRA_BASE_URL=https://your-site.atlassian.net
    JIRA_EMAIL=you@example.com
    JIRA_API_TOKEN=ATATT...   (create at https://id.atlassian.com/manage-profile/security/api-tokens)
    JIRA_PROJECT_KEY=KAN

Usage:
    python scripts/jira_sync.py           # dry run: checks access and prints the plan, changes nothing
    python scripts/jira_sync.py --apply   # creates the issues

Running it again is safe: every issue carries a label such as bk-ST-4, and
issues whose label already exists in the project are skipped.
"""
import csv
import os
import sys
import time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parents[1]
BACKLOG = ROOT / "docs" / "jira-backlog.csv"
TYPE_ORDER = {"Epic": 0, "Story": 1, "Task": 1, "Sub-task": 2}


def load_env() -> dict:
    values = {}
    for name in (".env.example", ".env"):
        path = ROOT / name
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if "=" in line and not line.lstrip().startswith("#"):
                    key, value = line.split("=", 1)
                    values[key.strip()] = value.strip()
    values.update({k: v for k, v in os.environ.items() if k.startswith("JIRA_")})
    return values


class Jira:
    def __init__(self, base: str, email: str, token: str):
        self.http = httpx.Client(base_url=base.rstrip("/"), auth=(email, token), timeout=30, headers={"Accept": "application/json"})

    def call(self, method: str, path: str, **kwargs):
        for _ in range(5):
            response = self.http.request(method, path, **kwargs)
            if response.status_code == 429:
                time.sleep(int(response.headers.get("Retry-After", "5")))
                continue
            return response
        return response


def adf(description: str, criteria: str, extra: list[str]) -> dict:
    paragraph = lambda text: {"type": "paragraph", "content": [{"type": "text", "text": text}]}
    content = [paragraph(description)] if description else []
    content += [paragraph(line) for line in extra]
    items = [c.strip() for c in criteria.split("|") if c.strip()]
    if items:
        content.append({"type": "heading", "attrs": {"level": 3}, "content": [{"type": "text", "text": "Acceptance criteria"}]})
        content.append({"type": "bulletList", "content": [{"type": "listItem", "content": [paragraph(item)]} for item in items]})
    return {"type": "doc", "version": 1, "content": content or [paragraph(" ")]}


def main(apply: bool) -> None:
    env = load_env()
    needed = ["JIRA_BASE_URL", "JIRA_EMAIL", "JIRA_API_TOKEN", "JIRA_PROJECT_KEY"]
    missing = [k for k in needed if not env.get(k) or env[k].lower() in ("xxx", "")]
    if missing:
        sys.exit(f"Set {', '.join(missing)} in .env first (see the top of this file).")
    if env["JIRA_API_TOKEN"].startswith("sk-"):
        sys.exit("JIRA_API_TOKEN looks like an OpenAI key. Create a Jira API token (it starts with ATATT) at https://id.atlassian.com/manage-profile/security/api-tokens")
    jira, key = Jira(env["JIRA_BASE_URL"], env["JIRA_EMAIL"], env["JIRA_API_TOKEN"]), env["JIRA_PROJECT_KEY"].upper()

    me = jira.call("GET", "/rest/api/3/myself")
    if me.status_code != 200:
        sys.exit(f"Jira login failed ({me.status_code}). Check JIRA_BASE_URL, JIRA_EMAIL and JIRA_API_TOKEN.")
    print(f"Signed in as {me.json().get('displayName')}")
    project = jira.call("GET", f"/rest/api/3/project/{key}")
    if project.status_code != 200:
        found = jira.call("GET", "/rest/api/3/project/search").json().get("values", [])
        sys.exit(f"Project {key} not found. Projects you can see: " + ", ".join(f"{p['key']} ({p['name']})" for p in found))
    project = project.json()
    print(f"Project {project['key']} · {project['name']} · {project.get('style', 'classic')}-managed")

    # Map our issue types to the project's own types.
    types = {}
    for item in project.get("issueTypes", []):
        name = item["name"].lower().replace("-", "")
        if item.get("subtask"):
            types["Sub-task"] = item
        elif item.get("hierarchyLevel") == 1 or name == "epic":
            types["Epic"] = item
        elif name in ("story", "task"):
            types[item["name"].title()] = item
    types.setdefault("Story", types.get("Task"))
    types.setdefault("Task", types.get("Story"))
    if not all(types.get(t) for t in TYPE_ORDER):
        sys.exit(f"The project is missing issue types: {[t for t in TYPE_ORDER if not types.get(t)]}")

    # Which optional fields each type accepts on its create screen.
    fields = {}
    for ours, item in types.items():
        meta = jira.call("GET", f"/rest/api/3/issue/createmeta/{key}/issuetypes/{item['id']}", params={"maxResults": 200})
        fields[ours] = {f["name"].lower(): f for f in meta.json().get("fields", meta.json().get("values", []))} if meta.status_code == 200 else {}

    def field_id(ours: str, *names: str):
        return next((fields[ours][n]["fieldId"] for n in names if n in fields[ours]), None)

    # Existing issues from an earlier run, found by their bk-* label.
    existing, token = {}, None
    while True:
        body = {"jql": f"project = {key} AND labels is not EMPTY", "fields": ["labels"], "maxResults": 100, **({"nextPageToken": token} if token else {})}
        page = jira.call("POST", "/rest/api/3/search/jql", json=body).json()
        for issue in page.get("issues", []):
            for label in issue["fields"].get("labels", []):
                if label.startswith("bk-"):
                    existing[label[3:]] = issue["key"]
        token = page.get("nextPageToken")
        if not token or page.get("isLast", True):
            break

    users = {}

    def account(name: str):
        if name and name not in users:
            found = jira.call("GET", "/rest/api/3/user/assignable/search", params={"project": key, "query": name}).json()
            exact = [u for u in found if isinstance(u, dict) and u.get("displayName", "").lower() == name.lower()]
            users[name] = exact[0]["accountId"] if len(exact) == 1 else None
        return users.get(name)

    rows = sorted(csv.DictReader(BACKLOG.open(encoding="utf-8")), key=lambda r: TYPE_ORDER[r["Issue Type"]])
    created = dict(existing)
    print(f"\n{len(rows)} backlog items · {len(existing)} already in Jira · {'APPLY' if apply else 'DRY RUN (add --apply to create)'}\n")
    for row in rows:
        ours, ident = row["Issue Type"], row["Issue ID"]
        if ident in created:
            print(f"  skip   {ident:7} {created[ident]:10} {row['Summary']}")
            continue
        assignee = account(row["Assignee"])
        sprint_label = "sprint-" + row["Sprint"].split()[1] if row["Sprint"] else None
        labels = [f"bk-{ident}", "elec5620"] + ([sprint_label] if sprint_label else []) + [l for l in row["Labels"].split(",") if l]
        extra = [f"Owner: {row['Assignee']}" + ("" if assignee else " (no matching Jira user; assign manually)"), f"Sprint: {row['Sprint']}"]
        data = {"project": {"key": key}, "issuetype": {"id": types[ours]["id"]}, "summary": row["Summary"][:250],
                "description": adf(row["Description"], row["Acceptance Criteria"], extra), "labels": labels}
        if row["Parent ID"]:
            data["parent"] = {"key": created.get(row["Parent ID"], f"<{row['Parent ID']}>")}
        if assignee:
            data["assignee"] = {"accountId": assignee}
        if "priority" in fields[ours] and row["Priority"]:
            data["priority"] = {"name": row["Priority"]}
        points = field_id(ours, "story point estimate", "story points")
        if points and row["Story Points"]:
            data[points] = float(row["Story Points"])
        epic_name = field_id(ours, "epic name")
        if epic_name and ours == "Epic":
            data[epic_name] = row["Summary"][:250]
        if not apply:
            print(f"  create {ident:7} {ours:8} parent={row['Parent ID'] or '-':6} {row['Status']:6} {row['Summary']}")
            created[ident] = f"<{ident}>"
            continue
        response = jira.call("POST", "/rest/api/3/issue", json={"fields": data})
        if response.status_code == 400:  # Retry without optional fields the project's screens may not allow.
            for optional in ("priority", points, "assignee"):
                data.pop(optional, None)
            response = jira.call("POST", "/rest/api/3/issue", json={"fields": data})
        if response.status_code not in (200, 201):
            print(f"  FAILED {ident}: {response.status_code} {response.text[:300]}")
            continue
        issue = response.json()["key"]
        created[ident] = issue
        status = row["Status"].strip()
        if status and status.lower() != "to do":
            transitions = jira.call("GET", f"/rest/api/3/issue/{issue}/transitions").json().get("transitions", [])
            category = "done" if status.lower() == "done" else "indeterminate"
            target = next((t for t in transitions if t["to"]["name"].lower() == status.lower()), None) or \
                next((t for t in transitions if t["to"].get("statusCategory", {}).get("key") == category), None)
            if target:
                jira.call("POST", f"/rest/api/3/issue/{issue}/transitions", json={"transition": {"id": target["id"]}})
        print(f"  ok     {ident:7} {issue:10} {row['Summary']}")
    if apply:
        print(f"\nDone. Open {env['JIRA_BASE_URL'].rstrip('/')}/jira/software/projects/{key}/list")
    unmatched = [name for name, acc in users.items() if not acc]
    if unmatched:
        print("No Jira user matched: " + ", ".join(unmatched) + ". Their issues say 'Owner: ...' in the description; assign them in Jira.")


if __name__ == "__main__":
    main("--apply" in sys.argv)
