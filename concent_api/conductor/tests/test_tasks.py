import mock

from django.test import TestCase

from golem_messages import message

from conductor.models import BlenderSubtaskDefinition
from conductor.models import VerificationRequest
from conductor.tasks import upload_acknowledged


class CoreTaskTestCase(TestCase):

    multi_db = True

    def setUp(self):
        self.source_package_path = 'blender/source/ef0dc1/ef0dc1.zzz523.zip'
        self.result_package_path = 'blender/result/ef0dc1/ef0dc1.zzz523.zip'
        self.scene_file = 'blender/scene/ef0dc1/ef0dc1.zzz523.zip'

        self.compute_task_def = message.ComputeTaskDef()
        self.compute_task_def['task_id'] = 'ef0dc1'
        self.compute_task_def['subtask_id'] = 'zzz523'

        self.verification_request = VerificationRequest(
            subtask_id=self.compute_task_def['subtask_id'],
            source_package_path=self.source_package_path,
            result_package_path=self.result_package_path,
        )
        self.verification_request.full_clean()
        self.verification_request.save()

        blender_subtask_definition = BlenderSubtaskDefinition(
            verification_request=self.verification_request,
            output_format=BlenderSubtaskDefinition.OutputFormat.JPG.name,  # pylint: disable=no-member
            scene_file=self.scene_file,
        )
        blender_subtask_definition.full_clean()
        blender_subtask_definition.save()

    def test_that_upload_acknowledged_task_should_change_upload_finished_on_existing_related_verification_request_to_true_and_call_blender_verification_order_task(self):
        with mock.patch('conductor.tasks.blender_verification_order.delay') as mock_blender_verification_order:
            upload_acknowledged(self.verification_request.subtask_id)

        self.verification_request.refresh_from_db()

        self.assertTrue(self.verification_request.upload_acknowledged)
        mock_blender_verification_order.assert_called_once_with(
            self.verification_request.subtask_id,
            self.verification_request.source_package_path,
            self.verification_request.result_package_path,
            self.verification_request.blender_subtask_definition.output_format,
            self.verification_request.blender_subtask_definition.scene_file,
        )

    def test_that_upload_acknowledged_task_should_log_error_when_verification_request_with_given_subtask_id_does_not_exist(self):
        with mock.patch('conductor.tasks.logging.error') as mock_logging_error:
            upload_acknowledged('non_existing_subtask_id')

        self.verification_request.refresh_from_db()

        self.assertFalse(self.verification_request.upload_acknowledged)
        mock_logging_error.assert_called_once_with(
            'Task `upload_acknowledged` tried to get VerificationRequest object with ID non_existing_subtask_id but it '
            'does not exist.'
        )
