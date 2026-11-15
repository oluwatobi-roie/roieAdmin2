"""GitHub runner: send only the tested source revision; never send local .env/data."""
import os
import json
from urllib.request import Request, urlopen
from pathlib import Path
import re
import shlex
import subprocess
import tempfile


def main():
    required = ['DEPLOY_HOST', 'DEPLOY_USER', 'DEPLOY_SSH_KEY', 'DEPLOY_KNOWN_HOSTS', 'DEPLOY_REVISION', 'DEPLOY_RUN']
    missing = [key for key in required if not os.environ.get(key, '').strip()]
    if missing:
        raise SystemExit('Configure these GitHub Actions secrets/variables: ' + ', '.join(missing))
    host, user = os.environ['DEPLOY_HOST'], os.environ['DEPLOY_USER']
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]*', host) or not re.fullmatch(r'[a-z_][a-z0-9_-]*', user):
        raise SystemExit('Invalid deployment host or SSH username.')
    port = int(os.environ.get('DEPLOY_PORT', '22'))
    if not 1 <= port <= 65535:
        raise SystemExit('Invalid SSH port.')
    revision = os.environ['DEPLOY_REVISION']
    run = os.environ['DEPLOY_RUN']
    if not re.fullmatch(r'[a-f0-9]{40}', revision) or not re.fullmatch(r'[0-9]+-[0-9]+', run):
        raise SystemExit('Invalid revision or run ID.')
    root = os.environ.get('DEPLOY_DIR', '/opt/roieadmin_v2')
    if not root.startswith('/') or root == '/' or '\n' in root:
        raise SystemExit('DEPLOY_DIR must be the existing absolute application folder.')
    token, repository = os.environ.get('GH_TOKEN'), os.environ.get('GITHUB_REPOSITORY')
    if token and repository:
        request = Request(f'https://api.github.com/repos/{repository}/git/ref/heads/main', headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'})
        with urlopen(request, timeout=20) as response:
            head = json.load(response)['object']['sha']
        if head != revision:
            print('A newer main revision exists; skipping this superseded deployment.')
            return
    release_id = revision + '-' + run
    remote = root.rstrip('/') + '/.deploy/releases/' + release_id
    with tempfile.TemporaryDirectory(prefix='roie-deploy-') as temporary:
        key = Path(temporary) / 'key'
        key.write_text(os.environ['DEPLOY_SSH_KEY'].strip() + '\n', encoding='utf-8')
        key.chmod(0o600)
        known = Path(temporary) / 'known_hosts'
        known.write_text(os.environ['DEPLOY_KNOWN_HOSTS'].strip() + '\n', encoding='utf-8')
        ssh = ['ssh', '-p', str(port), '-i', str(key), '-o', 'BatchMode=yes', '-o', 'IdentitiesOnly=yes',
               '-o', 'StrictHostKeyChecking=yes', '-o', f'UserKnownHostsFile={known}',
               '-o', 'ConnectTimeout=20', '-o', 'ServerAliveInterval=30', '-o', 'ServerAliveCountMax=6', f'{user}@{host}']
        archive = Path(temporary) / 'source.tar.gz'
        subprocess.run(['git', 'archive', '--format=tar.gz', '-o', str(archive), revision,
                        'backend', 'frontend', 'docker-compose.yml', 'deploy'], check=True)
        # mkdir must fail if this exact release already exists: do not overlay sources.
        command = f'umask 077; mkdir -p -- {shlex.quote(root + "/.deploy/releases")} && mkdir -- {shlex.quote(remote)} && tar -xzf - -C {shlex.quote(remote)}'
        with archive.open('rb') as stream:
            subprocess.run([*ssh, command], stdin=stream, check=True)
        command = shlex.join(['python3', remote + '/deploy/server_deploy.py', root, release_id])
        subprocess.run([*ssh, command], check=True)
        print(f'Deployed revision {revision}.')


if __name__ == '__main__':
    main()
