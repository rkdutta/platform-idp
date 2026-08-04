#!/usr/bin/env bash
#
# inspect-db.sh — read-only inspector for teams-api's live SQLite store.
#
# teams-api persists to SQLite at DATA_DIR (/data/teams.db in-cluster; WAL mode).
# This script execs into the running teams-api pod and reads the DB through a
# real sqlite3 connection (Python, always present in the app image) so that
# uncommitted-to-main WAL data is included and no separate sqlite3 CLI is needed.
# Every built-in mode is READ-ONLY (the `sql` mode refuses anything that isn't a
# SELECT/WITH/PRAGMA/EXPLAIN); `pull` uses SQLite's online-backup API for a
# consistent snapshot without quiescing the app.
#
# Usage:
#   ./inspect-db.sh [tables]            # tables + row counts (default)
#   ./inspect-db.sh schema              # full CREATE TABLE/INDEX DDL
#   ./inspect-db.sh dump [TABLE]        # all rows as JSON lines (all tables, or one)
#   ./inspect-db.sh sql "SELECT ..."    # run a read-only query, rows as JSON
#   ./inspect-db.sh pull [OUTFILE]      # consistent snapshot -> OUTFILE (default ./teams.db)
#
# Environment overrides:
#   NS=engineering-platform   APP_LABEL=app=teams-api   CONTAINER=teams-api   DB=/data/teams.db
#
set -euo pipefail

NS="${NS:-engineering-platform}"
APP_LABEL="${APP_LABEL:-app=teams-api}"
CONTAINER="${CONTAINER:-teams-api}"
DB="${DB:-/data/teams.db}"

cmd="${1:-tables}"
arg="${2:-}"

pod="$(kubectl get pods -n "$NS" -l "$APP_LABEL" \
  --field-selector=status.phase=Running \
  -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
if [[ -z "$pod" ]]; then
  echo "error: no Running pod for '$APP_LABEL' in namespace '$NS'" >&2
  exit 1
fi
echo "# pod=$pod ns=$NS db=$DB" >&2

# --- pull: consistent snapshot via SQLite online backup, then copy out --------
if [[ "$cmd" == "pull" ]]; then
  out="${arg:-./teams.db}"
  echo "# taking consistent snapshot..." >&2
  kubectl exec -i -n "$NS" "$pod" -c "$CONTAINER" -- \
    python3 -c 'import sqlite3,sys
s=sqlite3.connect(sys.argv[1]); d=sqlite3.connect("/tmp/teams-snapshot.db")
s.backup(d); d.close(); s.close()' "$DB"
  kubectl cp -c "$CONTAINER" "$NS/$pod:/tmp/teams-snapshot.db" "$out"
  kubectl exec -n "$NS" "$pod" -c "$CONTAINER" -- rm -f /tmp/teams-snapshot.db
  echo "# wrote $out" >&2
  exit 0
fi

# --- everything else: stream the reader script to the pod's python ------------
# Script comes in on stdin (python3 -), mode/db/arg come in as argv.
kubectl exec -i -n "$NS" "$pod" -c "$CONTAINER" -- python3 - "$cmd" "$DB" "$arg" <<'PY'
import sqlite3, sys, json

mode = sys.argv[1]
db   = sys.argv[2]
arg  = sys.argv[3] if len(sys.argv) > 3 and sys.argv[3] != "" else None

con = sqlite3.connect(db, timeout=5)
con.row_factory = sqlite3.Row
cur = con.cursor()

def tables():
    return [r[0] for r in cur.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]

def jdefault(o):
    if isinstance(o, (bytes, bytearray)):
        return "<blob %d bytes>" % len(o)
    return str(o)

if mode in ("tables", "count"):
    print("%-34s %8s" % ("TABLE", "ROWS"))
    print("-" * 43)
    for t in tables():
        n = cur.execute('SELECT COUNT(*) FROM "%s"' % t).fetchone()[0]
        print("%-34s %8d" % (t, n))

elif mode == "schema":
    for r in cur.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%' "
        "ORDER BY type DESC, name"):
        print(r[0].strip() + ";\n")

elif mode == "dump":
    tabs = [arg] if arg else tables()
    for t in tabs:
        rows = cur.execute('SELECT * FROM "%s"' % t).fetchall()
        print("### %s (%d rows)" % (t, len(rows)))
        for row in rows:
            print(json.dumps(dict(row), default=jdefault, ensure_ascii=False))
        print()

elif mode == "sql":
    q = (arg or "").strip()
    head = q.split(None, 1)[0].lower() if q else ""
    if head not in ("select", "with", "pragma", "explain"):
        sys.stderr.write(
            "refusing non-read query (must start with SELECT/WITH/PRAGMA/EXPLAIN)\n")
        sys.exit(2)
    rows = cur.execute(q).fetchall()
    for row in rows:
        print(json.dumps(dict(row), default=jdefault, ensure_ascii=False))
    sys.stderr.write("(%d rows)\n" % len(rows))

else:
    sys.stderr.write("unknown command: %s\n" % mode)
    sys.exit(64)

con.close()
PY
