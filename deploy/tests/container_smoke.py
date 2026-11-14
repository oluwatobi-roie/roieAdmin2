"""Optional local Docker smoke test. Uses isolated names, SQLite, no host ports/data."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from server_deploy import healthy


def main():
    project = 'roiepipelineqa' + uuid.uuid4().hex[:10]
    with tempfile.TemporaryDirectory(prefix='roie-pipeline-qa-') as directory:
        config = Path(directory) / 'compose.json'
        config.write_text(json.dumps({'services': {
            'backend': {'image': 'roieadmin-backend-pipeline-check', 'environment': {'TRACCAR_API_URL': 'https://traccar.invalid/api/', 'DATABASE_URL': 'sqlite:///:memory:'}, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'], 'tmpfs': ['/tmp']},
            'frontend': {'image': 'roieadmin-frontend-pipeline-check', 'environment': {'BACKEND_URL': 'http://backend:5000', 'NODE_ENV': 'production'}, 'read_only': True, 'cap_drop': ['ALL'], 'security_opt': ['no-new-privileges:true'], 'tmpfs': ['/tmp', '/app/.next/cache']}
        }, 'networks': {'default': {'internal': True}}}),encoding='utf-8')
        compose = ['docker', 'compose', '--project-name', project, '-f', str(config)]
        try:
            subprocess.run([*compose, 'up', '-d', '--no-build', '--pull', 'never'],check=True)
            if not healthy(compose):
                subprocess.run([*compose, 'logs', '--tail', '30'])
                raise RuntimeError('Container integration smoke test failed.')
            print('PASS: isolated backend HTTP + SQLite, frontend page + runtime backend proxy.')
        finally:
            subprocess.run([*compose, 'down'],check=True)


if __name__ == '__main__':
    main()
