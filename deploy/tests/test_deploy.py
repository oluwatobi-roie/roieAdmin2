import sys
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server_deploy as deployment


class DeploymentTests(unittest.TestCase):
    def test_same_project_keeps_existing_volume_namespace(self):
        container = {'Config': {'Labels': {'com.docker.compose.project': 'roieadmin_v2'}}}
        self.assertEqual(deployment.same_project(container, container), 'roieadmin_v2')
        with self.assertRaises(RuntimeError):
            deployment.same_project(container, {'Config': {'Labels': {}}})

    def test_existing_finance_volume_is_reused_by_exact_name(self):
        override = deployment.finance_volume_override({'Mounts': [{'Destination': '/app/data/finance', 'Type': 'volume', 'Name': 'existing-billing-data'}]})
        self.assertEqual(override['volumes']['finance_data'], {'external': True, 'name': 'existing-billing-data'})
        self.assertEqual(deployment.finance_volume_override({'Mounts': []}), {})
        with self.assertRaises(RuntimeError):
            deployment.finance_volume_override({'Mounts': [{'Destination': '/app/data/finance', 'Type': 'bind'}]})

    def test_success_builds_before_restart_without_down_or_volume_removal(self):
        with patch.object(deployment, 'run') as run, patch.object(deployment, 'healthy', return_value=True):
            deployment.rollout(['new'], ['old'])
        self.assertEqual(run.call_args_list[0].args[0], ['new', 'build', 'backend', 'frontend'])
        self.assertEqual(run.call_args_list[1].args[0], ['new', 'up', '-d', '--no-build', '--pull', 'never', '--no-deps', 'backend', 'frontend'])
        self.assertEqual(run.call_count, 2)

    def test_build_failure_does_not_restart_any_containers(self):
        with patch.object(deployment, 'run', side_effect=subprocess.CalledProcessError(1, 'build')) as run:
            with self.assertRaises(subprocess.CalledProcessError):
                deployment.rollout(['new'], ['old'])
        self.assertEqual(run.call_count, 1)

    def test_health_failure_restores_previous_images_and_reports_failure(self):
        with patch.object(deployment, 'run') as run, patch.object(deployment, 'healthy', side_effect=[False, True]):
            with self.assertRaisesRegex(RuntimeError, 'new containers failed'):
                deployment.rollout(['new'], ['old'])
        self.assertEqual(run.call_args_list[-1].args[0][0], 'old')
        self.assertIn('--no-build', run.call_args_list[-1].args[0])

    def test_partial_restart_failure_also_rolls_back(self):
        with patch.object(deployment, 'run', side_effect=[None, subprocess.CalledProcessError(1, 'up'), None]) as run, patch.object(deployment, 'healthy', return_value=True):
            with self.assertRaises(subprocess.CalledProcessError):
                deployment.rollout(['new'], ['old'])
        self.assertEqual(run.call_args_list[-1].args[0][0], 'old')

    def test_failed_rollback_does_not_report_success(self):
        with patch.object(deployment, 'run'), patch.object(deployment, 'healthy', side_effect=[False, False]):
            with self.assertRaisesRegex(RuntimeError, 'readiness checks still fail'):
                deployment.rollout(['new'], ['old'])


if __name__ == '__main__':
    unittest.main()
