"""Run on the Linux Docker host. Preserve the existing Compose project and volumes."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


def run(args, capture=False):
    return subprocess.run(args, check=True, text=True, stdout=subprocess.PIPE if capture else None).stdout


def inspect(name):
    return json.loads(run(['docker', 'inspect', name], capture=True))[0]


def same_project(backend, frontend):
    projects = [(item.get('Config', {}).get('Labels') or {}).get('com.docker.compose.project') for item in (backend, frontend)]
    if not projects[0] or projects[0] != projects[1]:
        raise RuntimeError('admin_backend and admin_frontend must belong to the same existing Compose project.')
    return projects[0]


def finance_volume_override(container):
    mounts = [mount for mount in container.get('Mounts', []) if mount['Destination'] == '/app/data/finance']
    if not mounts:
        return {}
    mount = mounts[0]
    if mount.get('Type') != 'volume' or not mount.get('Name'):
        raise RuntimeError('Finance uses a custom bind mount. Preserve it explicitly before enabling this pipeline.')
    return {'volumes': {'finance_data': {'external': True, 'name': mount['Name']}}}


BACKEND_CHECK = '''import urllib.request, urllib.error
try:
    urllib.request.urlopen('http://127.0.0.1:5000/backend/auth/check-session', timeout=5)
    raise RuntimeError('Expected an unauthenticated response')
except urllib.error.HTTPError as error:
    assert error.code == 401
from app import app
from config import db
from sqlalchemy import text
with app.app_context():
    assert db.session.execute(text('SELECT 1')).scalar() == 1
'''
FRONTEND_CHECK = """const host=process.env.HOSTNAME&&process.env.HOSTNAME!=='0.0.0.0'?process.env.HOSTNAME:'127.0.0.1';const base='http://'+host+':3000';Promise.all([fetch(base+'/login'),fetch(base+'/api/auth/check-session')]).then(([page,api])=>{if(page.status!==200||api.status!==401)process.exit(1)}).catch(()=>process.exit(1));"""


def healthy(compose, timeout=90):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            for service, command in [('backend', ['/usr/bin/python3', '-c', BACKEND_CHECK]), ('frontend', ['/nodejs/bin/node', '-e', FRONTEND_CHECK])]:
                subprocess.run([*compose, 'exec', '-T', service, *command], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
            return True
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            time.sleep(3)
    return False


def rollout(compose, rollback_compose):
    # Build completes while the current containers continue serving traffic.
    run([*compose, 'build', 'backend', 'frontend'])
    try:
        run([*compose, 'up', '-d', '--no-build', '--pull', 'never', '--no-deps', 'backend', 'frontend'])
        if not healthy(compose):
            raise RuntimeError('The new containers failed HTTP/database readiness checks.')
    except Exception:
        print('Deployment failed; restoring the previous container images.', flush=True)
        run([*rollback_compose, 'up', '-d', '--no-build', '--pull', 'never', '--no-deps', 'backend', 'frontend'])
        if not healthy(rollback_compose):
            raise RuntimeError('Previous images restored, but readiness checks still fail. Inspect the server.')
        raise


def deploy(root, release_id):
    root = Path(root).resolve(strict=True)
    if not re.fullmatch(r'[a-f0-9]{40}-[0-9]+-[0-9]+', release_id):
        raise RuntimeError('Invalid release identifier.')
    release = (root / '.deploy' / 'releases' / release_id).resolve(strict=True)
    if release.parent != (root / '.deploy' / 'releases').resolve() or not (release / 'docker-compose.yml').is_file():
        raise RuntimeError('Release must be inside this application’s .deploy/releases folder.')
    for relative in ('.env', 'backend/.env'):
        source = root / relative
        if not source.is_file():
            raise RuntimeError(f'Missing server configuration file: {source}. See DEPLOYMENT.md.')
        target = release / relative
        if target.exists() or target.is_symlink():
            raise RuntimeError(f'{relative} must not be committed in the deployment archive.')
        target.symlink_to(source)
    backend, frontend = inspect('admin_backend'), inspect('admin_frontend')
    project = same_project(backend, frontend)
    volume_override = finance_volume_override(backend)
    for container in (backend, frontend):
        working_dir = (container['Config'].get('Labels') or {}).get('com.docker.compose.project.working_dir', '')
        if Path(working_dir).resolve() != root and not Path(working_dir).resolve().is_relative_to(root / '.deploy' / 'releases'):
            raise RuntimeError('Running containers belong to a different folder; refusing to replace them.')
    run(['docker', 'network', 'inspect', 'roie_net'], capture=True)
    images, previous = {}, {}
    for service, container in [('backend', backend), ('frontend', frontend)]:
        images[service] = {'image': f'roieadmin-deploy-{service}:{release_id}'}
        old_tag = f'roieadmin-previous-{service}:{release_id}'
        run(['docker', 'tag', container['Image'], old_tag])
        previous[service] = {'image': old_tag}
    image_file, rollback_file = release / 'images.json', release / 'previous-images.json'
    image_file.write_text(json.dumps({'services': images, **volume_override}), encoding='utf-8')
    rollback_file.write_text(json.dumps({'services': previous, **volume_override}), encoding='utf-8')
    base = ['docker', 'compose', '--project-name', project, '--env-file', str(root / '.env'), '-f', str(release / 'docker-compose.yml')]
    compose, rollback = [*base, '-f', str(image_file)], [*base, '-f', str(rollback_file)]
    configuration = json.loads(run([*compose, 'config', '--format', 'json'], capture=True))
    if not configuration['services']['backend'].get('environment', {}).get('DATABASE_URL'):
        raise RuntimeError('Set the working production DATABASE_URL in backend/.env before deployment.')
    # A changed Compose project would create a different invoice volume. It is kept explicit above.
    rollout(compose, rollback)
    temporary = root / '.deploy' / f'current.{release_id}.tmp'
    temporary.symlink_to(release, target_is_directory=True)
    os.replace(temporary, root / '.deploy' / 'current')
    print(f'Healthy release: {release_id}; Compose project: {project}', flush=True)


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: server_deploy.py /opt/roieadmin_v2 COMMIT-RUN-ATTEMPT')
    import fcntl
    root = Path(sys.argv[1]).resolve(strict=True)
    (root / '.deploy').mkdir(mode=0o700, exist_ok=True)
    with (root / '.deploy' / 'deploy.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        deploy(root, sys.argv[2])


if __name__ == '__main__':
    main()
