# platform-idp — application source for the IDP

This repo holds the **application source code** for the self-service internal
developer platform: the Projects (née "Teams") UI, API, reconciler, and CLI.
It is one of several sibling repos under a `capstone-project` umbrella and has
its **own git remote** (`git@github.com:rkdutta/platform-idp.git`) — commits
here don't imply commits in `platform-infra` (GitOps manifests) or
`platform-base` (Terraform/cluster). A feature that changes behavior *and* what
runs in-cluster usually needs a commit **here** (code) **and** in
`platform-infra` (the `image:` tag bump).

> `../CLAUDE.md` (capstone-project root) has the platform-wide map and a
> high-level description; `../platform-infra/CLAUDE.md` and
> `../platform-base/CLAUDE.md` have the cluster/GitOps features and the
> hard-won operational gotchas. **Read those for anything touching the
> running cluster.** This file covers what's specific to developing *this*
> repo: the app source, local run/test loop, and release pipeline.

## What this repo delivers

The **Projects** self-service model (renamed from "Teams" mid-development —
see gotchas below): a project owner gets one or more k8s namespaces, and
every cluster-side consequence of that is reconciled continuously from here:

- **teams-api** — the source of truth (ownership, namespace membership,
  tiers) and the human-facing REST API; also serves `GET /kubeconfig` (OIDC
  `kubectl` access) and syncs grants/revokes into Keycloak group membership
  live, with a periodic reconcile pass (`GROUP_RECONCILE_INTERVAL`, default
  60s) as a self-healing backstop against a missed sync.
- **teams-operator** — watches teams-api's state (`kopf`) and reconciles it
  onto the cluster: k8s RBAC (RoleBindings on the built-in `view`/`edit`
  ClusterRoles + a `teams-admins` ClusterRoleBinding), the per-project Argo
  CD RBAC Casbin block, OpenBao access (both the SPIFFE/SPIRE workload path
  and the human-OIDC-SSO path, via `ensure_openbao_access` /
  `_ensure_openbao_group_alias`), quotas/limits/network policy, and the
  Harbor pull secret — and tears all of it (including real OpenBao secret
  data) back down when a project is deleted. See `../platform-infra/CLAUDE.md`
  for what these targets look like on the cluster side.
- **teams-app** — the UI; deep-links out to Argo CD, the Argo Rollouts
  dashboard, and OpenBao (the "Secrets" button lands on OpenBao's
  create-secret form, not the list view — a brand-new project has nothing to
  list yet).
- **teams-cli** — the same self-service surface from a terminal, feeding
  `kubectl`'s OIDC login.

**Pending**: the operator/API/UI side of self-service cloud resource
provisioning (a `ResourceAccess`) — teams-operator's OpenBao/SPIFFE access
wiring + teardown for provisioned cloud resources, and the teams-api/
teams-app request path. Crossplane's side (XRDs/Compositions, provider
credentials) is being built in `platform-infra` — full design in
`platform-infra/docs/multicloud-resource-access.md`.

## Monorepo layout (`teams-management/`)

Four components, one **unified version** (a single `vX.Y.Z` tag releases all of
them — see Releases):

| Path | Component | Stack | Notes |
|---|---|---|---|
| `teams-management/teams-api` | Projects API | Python / FastAPI, SQLite | Entry `main.py` (~1.5k lines); persistence `store.py`; authz `auth.py`/`authz.py`; Keycloak admin `keycloak_admin.py`. |
| `teams-management/teams-operator` | Reconciler | Python / kopf | Single file `teams_operator.py` (~2.2k lines). Reconciles k8s RBAC, Argo CD RBAC, OpenBao/SPIFFE access, quotas, Harbor pull secrets from teams-api state. |
| `teams-management/teams-app` | Projects UI | Angular / TypeScript, nginx | `src/`; deep-links to Argo CD / Rollouts / OpenBao. |
| `teams-management/teams-cli` | CLI | Python (single `teams_cli.py`) | Released as PyInstaller `--onefile` binaries. |

`teams-management/teams-realm.json` is the **local/compose** Keycloak realm
import. The **k8s** realm lives in `platform-infra`
(`apps/security/keycloak/`), which itself keeps *two* in-sync copies. Treat
Keycloak realm config as a multi-copy-by-hand artifact: when you change a
client/role/group, grep all copies.

## Run locally

```bash
cd teams-management
docker compose up --build      # postgres + keycloak + teams-api + teams-app
```

Ports: teams-app `:4201`, teams-api `:8085` (→ container `:8000`), Keycloak
`:8180`, postgres `:5432`. teams-app's browser-facing URLs (`API_URL`,
`KEYCLOAK_URL`) are **baked in at build time** via `Dockerfile.compose` build
args — changing them means a rebuild, not just an env var. Locally teams-api's
SQLite store is redirected to `/tmp/teams-api-data` (the real `/data` PVC path
403s for the non-root container without a volume).

## Test

Only `teams-api` has a suite today (`tests/`, RBAC-focused). It runs without
Keycloak or a network (KeycloakAdmin degrades to "unknown user"), and
`conftest.py` redirects `DATA_DIR` to a temp dir before importing `store`, so a
run can never touch a real volume.

```bash
cd teams-management/teams-api
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt -r requirements-dev.txt
.venv/bin/python -m pytest tests/ -q
```

Note the `httpx==0.27.2` pin in `requirements-dev.txt`: FastAPI 0.104's
Starlette predates httpx 0.28's `Client()` signature change, so a newer httpx
breaks `TestClient`. Don't "upgrade" it casually.

Quick sanity for the operator / non-tested modules: `python3 -m py_compile
teams_operator.py` etc.

## Build & deploy an image (the cross-repo loop)

The real Dockerfiles (NOT the plain `Dockerfile` for teams-app):

| Component | Dockerfile |
|---|---|
| teams-api | `teams-api/Dockerfile` |
| teams-operator | `teams-operator/operator.Dockerfile` |
| teams-app | `teams-app/Dockerfile.k8s` |

For a local cluster iteration (see the root CLAUDE.md for the full, gotcha-laden
version):

1. Build tagged `harbor.127.0.0.1.sslip.io/platform/<app>:<next-version>`.
2. **Pushing to Harbor from the host needs the `:8443` port** — the bare
   hostname resolves to 443, which nothing listens on host-side.
3. **Always also `kind load docker-image ... --name platform-base`** as a
   reliable fallback — `imagePullPolicy: IfNotPresent` means a preloaded image
   skips the flaky Harbor path entirely.
4. Bump the `image:` tag in the app's manifest **in `platform-infra`**, commit
   + push both repos (code here, tag there).
5. Argo CD polling lags; hard-refresh may be needed per **child** Application,
   not just `root`.

## Releases (CI)

`.github/workflows/release.yml`:

- **`v*` tag → full release**: multi-arch images to GHCR, **cosign keyless**
  signed + SBOM/vuln attested + re-verified (fail closed), Trivy gate on
  CRITICAL, plus PyInstaller CLI binaries with a cosign-signed `SHA256SUMS`,
  bundled into a GitHub Release. Harbor pull-replicates the images to
  `platform/<component>:<version>`.
- **PR → `pr-scan`**: builds each image and fails on CRITICAL CVEs. No push, no
  signing.
- **No rolling `main` builds** — only `v*` tags produce artifacts, deliberately
  (keeps GHCR/cosign from accumulating a sig/att pair per throwaway commit). So:
  cut a tag to release; don't expect a push to `main` to build anything.

The keyless signing identity is `rkdutta/<repo>/.github/workflows/release.yml
@ refs/tags/v*`, which matches the cluster's Ratify admission trust policy —
images built this way are admission-verifiable without a policy change.

## Repo-specific gotchas

- **The in-repo k8s manifests are stale reference, not the deploy source.**
  `teams-api/deployment.yaml`, `teams-operator/operator-deployment.yaml`, and
  `teams-app/k8s/*` still point at `olivercodes01/*` template images. The
  **live** manifests (with `harbor.../platform/*` images and real tags) live in
  `platform-infra`. Editing these files does **not** change what's deployed —
  bump the tag in `platform-infra` instead.
- **"Projects" vs "Teams" naming.** The product renamed Teams → Projects
  mid-development, but DB tables (`team_*`) and some Keycloak roles
  (`team-leader`) still say "team" on purpose. Don't "fix" those without
  checking the migration/impact — they're load-bearing legacy names.
- **teams-api persistence is SQLite** at `DATA_DIR` (`/data` PVC in k8s, `/tmp`
  locally). It's a real file store, not in-memory (the old README says
  in-memory — outdated).
- **Keycloak realm lives in multiple hand-synced copies** (see above).
- **`_emit_event` 422s on cluster-scoped objects.** `teams_operator.py`'s
  `_emit_event` gets `422 Unprocessable Entity` ("does not match
  event.namespace") whenever the involved object is cluster-scoped (e.g. a
  `ClusterRoleBinding`) or its target namespace is already gone — logged
  every reconcile cycle, harmless, never blocks reconciliation. Low-priority
  cleanup if ever picked up.
