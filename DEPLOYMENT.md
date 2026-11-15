# Automatic deployment to /opt/roieadmin_v2

The pipeline is `.github/workflows/deploy.yml`. Production branch: **main**.
Server: **45.32.179.99**. Application directory: **/opt/roieadmin_v2**.

Your normal flow becomes:

```text
Edit/test on laptop → commit/push → merge into main → GitHub checks
→ SSH upload of that exact revision → Docker builds on server
→ replace backend/frontend → HTTP and database readiness checks
```

Changes on `sync-server-code` do not deploy until merged into `main`.
The files are prepared locally; GitHub secrets and the server key must be configured before deployment can run.

## 1. Check the existing server setup

Connect using your normal SSH key and passphrase. Run on the server:

```bash
cd /opt/roieadmin_v2
python3 --version
docker compose version
test -f .env && echo 'Compose .env exists'
test -f backend/.env && echo 'Backend .env exists'
docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' admin_backend
docker inspect --format '{{index .Config.Labels "com.docker.compose.project"}}' admin_frontend
docker inspect --format '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' admin_backend
```

Python 3.9+ and Docker Compose v2 are required. Both containers must belong to the same Compose project and this application folder. The script discovers and preserves that project name, including its finance volume.

Keep the existing real configuration **on the server**:

- `/opt/roieadmin_v2/.env`: existing Compose variables: `TRACCAR_API_URL`, `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `NEXT_PUBLIC_BACKEND_URL`.
- `/opt/roieadmin_v2/backend/.env`: `DATABASE_URL`, `TRACCAR_API_URL`, and `TRACCAR_ADMIN_KEY` where used by your existing account actions.

The database URL must be the working **server/Docker** URL, normally using `mysql57:3306`; do not copy the laptop's SSH-tunnel URL. Keep the real credentials unchanged. The frontend builder, runtime, and GitHub checks now use Node 24; the old Node 20.11 builder could not load the locked frontend dependencies. The updated Compose file injects backend/.env at runtime; Docker no longer copies it into images. Next's API routes use `BACKEND_URL=http://backend:5000` inside Docker.

If a file is missing, create it using your existing production configuration before enabling deployments. Do not paste secret values into chat or commit them. Keep the external Docker network `roie_net` and existing MySQL container as they are.

## 2. Make a separate SSH key for GitHub

Your personal SSH key and its passphrase stay on your laptop. GitHub needs a separate unattended key.

Run in **PowerShell on your laptop**:

```powershell
ssh-keygen -t ed25519 -C "roieadmin-github-actions" -f "$env:USERPROFILE\.ssh\roieadmin_actions"
```

When asked for a passphrase, press Enter twice for this dedicated automation key. If that filename already exists, choose another name instead of overwriting it.

Add its **public** key to the server using your normal key:

```powershell
$deployPublicKey = (Get-Content "C:\Users\engrt\Desktop\Running_Roie_Apps\roieadmin\Tools\roieadmin_action.pub" -Raw).Trim()
"restrict $deployPublicKey" | ssh -i "C:\Users\engrt\Desktop\Running_Roie_Apps\roieadmin\Tools\id_ed25519" root@45.32.179.99 "umask 077; mkdir -p /root/.ssh; cat >> /root/.ssh/authorized_keys"
```

Enter your normal key's passphrase when prompted. This adds a new authorized key; it does not replace your existing login key. `restrict` disables forwarding and interactive terminal allocation for the automation key while allowing deployment commands.

Test it from PowerShell (no passphrase should be requested):

```powershell
ssh -i "C:\Users\engrt\Desktop\Running_Roie_Apps\roieadmin\Tools\roieadmin_action" -o BatchMode=yes root@45.32.179.99 "docker compose version"
```

This configuration uses your existing root account. Protect the automation private key like a server credential; it can run deployment commands as root.

## 3. Add four GitHub repository secrets

Open your repository → **Settings → Secrets and variables → Actions → Secrets → New repository secret**.

| Secret | Value |
| --- | --- |
| `DEPLOY_HOST` | `45.32.179.99` |
| `DEPLOY_USER` | `root` |
| `DEPLOY_SSH_KEY` | Complete contents of the dedicated `roieadmin_actions` private key, including BEGIN/END lines |
| `DEPLOY_KNOWN_HOSTS` | The server's verified host-key line, obtained below |

To copy the private key to your clipboard without printing it:

```powershell
Get-Content "$env:USERPROFILE\.ssh\roieadmin_actions" -Raw | Set-Clipboard
```

Paste into `DEPLOY_SSH_KEY`, save, then clear the clipboard:

```powershell
Set-Clipboard -Value ''
```

For `DEPLOY_KNOWN_HOSTS`, use your **existing trusted SSH session on the server** and run:

```bash
awk '{print "45.32.179.99 " $1 " " $2}' /etc/ssh/ssh_host_ed25519_key.pub
```

Copy the resulting single line into `DEPLOY_KNOWN_HOSTS`. This is the server identity, not your login key. The workflow verifies it strictly; it does not blindly trust a new SSH host key. If SSH uses a nonstandard port, set repository variable `DEPLOY_PORT` and use `[45.32.179.99]:PORT` as the host field in that line.

## 4. Publish the prepared pipeline

From the laptop repository root, review the changes, then commit/push your current branch:

```powershell
git diff
git add .github deploy DEPLOYMENT.md docker-compose.yml frontend/Dockerfile frontend/.dockerignore backend/.dockerignore .gitignore frontend/src/app/api
git commit -m "Add tested SSH deployment pipeline"
git push -u origin sync-server-code
```

Open a pull request from `sync-server-code` to `main` in GitHub and merge it after checks pass. This includes any application updates already committed to that branch. The pipeline file must be on `main` for the normal manual-run button to appear.

## 5. Run once, then enable automatic updates

In GitHub, open **Actions → Check and deploy RoieAdmin → Run workflow**, selecting **main**.

The manual run performs checks and deployment. Watch the log for `Healthy release` and check your application afterward. Once ready, add a repository **variable** (not a secret) under **Settings → Secrets and variables → Actions → Variables**:

| Variable | Value |
| --- | --- |
| `DEPLOY_ENABLED` | `true` |

Every subsequent push/merge into `main` then triggers deployment automatically. Remove the variable or set it to `false` to stop automatic deployment; manual runs on main remain available.

You do not need to keep your laptop's database SSH tunnel open for deployments. GitHub connects directly to the server using its dedicated key. No GitHub clone credentials are required on the server because GitHub uploads a source archive.

## What deployment changes

- Creates a separate source folder at `.deploy/releases/COMMIT-RUN-ATTEMPT` under the application folder.
- Links the server's existing `.env` files into that release; does not upload laptop settings or finance records.
- Builds both images on the server while current containers continue serving.
- Replaces only `admin_backend` and `admin_frontend`. It never runs `docker compose down`, deletes volumes, or restarts MySQL, Nominatim, rentals or other applications.
- Checks backend HTTP readiness, a read-only database `SELECT 1`, frontend login rendering and the frontend-to-backend API connection.
- Attempts to restore the previous images if replacement or readiness fails. A failed build leaves the running containers untouched.
- Serializes deployments and skips a queued commit if main already has a newer revision.
- Records the last successful release through `.deploy/current`.

This is a single-server deployment with a brief interruption while containers restart, not zero-downtime blue/green deployment. Automatic rollback restores previous **images** using the same new Compose configuration and server environment; it cannot undo database migrations or configuration changes. Keep a backup of the finance volume, including payment screenshots. Current finance releases do not change the database schema.

Release folders and previous image tags are retained for diagnosis; monitor disk usage and remove old releases deliberately when they are no longer needed. The pipeline does not prune Docker images or delete data automatically.

## Routine updates and diagnostics

Continue working locally, push your feature branch, and merge into main. GitHub Actions reports test/build/deployment status for each change.

On the server, basic diagnostics remain:

```bash
docker ps --filter name=admin_
docker logs --tail 100 admin_backend
docker logs --tail 100 admin_frontend
readlink -f /opt/roieadmin_v2/.deploy/current
```

After the first automated deployment, the root folder's source checkout is no longer the live release. Do not run a stale root-folder `docker compose up` to apply code updates. Use the pipeline. To undo a successful application change, revert its commit on main and push the revert so the tested pipeline deploys it.

GitHub must be able to reach the server's SSH port. An SSH timeout means to check routing/firewall access; `Permission denied (publickey)` means to check the dedicated public key and matching GitHub secret. Host-key errors require checking the server identity again through your trusted SSH access. Do not disable host-key verification.

Official references: [GitHub Actions deployments](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments), [Docker Compose up](https://docs.docker.com/reference/cli/docker/compose/up/), [Docker build exclusions](https://docs.docker.com/build/concepts/context/#dockerignore-files).
