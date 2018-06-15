from zipfile import BadZipFile
from subprocess import SubprocessError
import logging
import os

from celery import shared_task
from golem_messages import message
from requests import HTTPError

from django.conf import settings

from conductor.models import BlenderSubtaskDefinition
from core.constants import VerificationResult
from core.tasks import verification_result
from core.transfer_operations import create_file_transfer_token_for_concent
from core.transfer_operations import send_request_to_storage_cluster
from gatekeeper.constants import CLUSTER_DOWNLOAD_PATH
from utils.constants import ErrorCode
from utils.decorators import provides_concent_feature
from .utils import clean_directory
from .utils import delete_file
from .utils import get_files_list_from_archive
from .utils import prepare_storage_request_headers
from .utils import run_blender
from .utils import store_file_from_response_in_chunks
from .utils import unpack_archive


logger = logging.getLogger(__name__)


@shared_task
@provides_concent_feature('verifier')
def blender_verification_order(
    subtask_id: str,
    source_package_path: str,
    source_size: int,
    source_package_hash: str,
    result_package_path: str,
    result_size: int,
    result_package_hash: str,
    output_format: str,
    scene_file: str,  # pylint: disable=unused-argument
):
    assert output_format in BlenderSubtaskDefinition.OutputFormat.__members__.keys()
    assert source_package_path != result_package_path
    assert source_package_hash != result_package_hash
    assert (source_size and source_package_hash and source_package_path) and (result_size and result_package_hash and result_package_path)
    assert isinstance(subtask_id, str)

    # this is a temporary hack - dummy verification which's result depends on subtask_id only
    if settings.MOCK_VERIFICATION_ENABLED:
        if subtask_id[-1] == 'm':
            verification_result.delay(
                subtask_id,
                VerificationResult.MATCH.name,
            )
        else:
            verification_result.delay(
                subtask_id,
                VerificationResult.MISMATCH.name,
            )
        return

    # Generate a FileTransferToken valid for a download of any file listed in the order.
    file_transfer_token = create_file_transfer_token_for_concent(
        subtask_id=subtask_id,
        source_package_path=source_package_path,
        source_size=source_size,
        source_package_hash=source_package_hash,
        result_package_path=result_package_path,
        result_size=result_size,
        result_package_hash=result_package_hash,
        operation=message.FileTransferToken.Operation.download,
    )

    # Remove any files from VERIFIER_STORAGE_PATH.
    clean_directory(settings.VERIFIER_STORAGE_PATH)

    package_paths_to_downloaded_file_names = {
        source_package_path: f'source_{os.path.basename(source_package_path)}',
        result_package_path: f'result_{os.path.basename(result_package_path)}',
    }

    # Download all the files listed in the message from the storage server to local storage.
    for file_path, download_file_name in package_paths_to_downloaded_file_names.items():
        try:
            file_transfer_token.sig = None
            cluster_response = send_request_to_storage_cluster(
                prepare_storage_request_headers(file_transfer_token),
                settings.STORAGE_CLUSTER_ADDRESS + CLUSTER_DOWNLOAD_PATH + file_path,
                method='get',
            )
            store_file_from_response_in_chunks(
                cluster_response,
                os.path.join(
                    settings.VERIFIER_STORAGE_PATH,
                    download_file_name,
                )
            )

        except (OSError, HTTPError) as exception:
            logger.info(f'blender_verification_order for SUBTASK_ID {subtask_id} failed with error {exception}.')
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR.name,
                str(exception),
                ErrorCode.VERIFIIER_FILE_DOWNLOAD_FAILED.name
            )
            return
        except Exception as exception:
            logger.info(f'blender_verification_order for SUBTASK_ID {subtask_id} failed with error {exception}.')
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR.name,
                str(exception),
                ErrorCode.VERIFIIER_FILE_DOWNLOAD_FAILED.name
            )
            raise

    # Verifier unpacks the archive with project source.
    for file_path, download_file_name in package_paths_to_downloaded_file_names.items():
        try:
            unpack_archive(download_file_name)
        except (OSError, BadZipFile) as e:
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR.name,
                str(e),
                ErrorCode.VERIFIIER_UNPACKING_ARCHIVE_FAILED.name
            )
            return

    # Verifier runs blender process.
    try:
        completed_process = run_blender(
            scene_file,
            output_format,
        )
        logger.info(f'Blender process std_out: {completed_process.stdout}')
        logger.info(f'Blender process std_err: {completed_process.stdout}')

        # If Blender finishes with errors, verification ends here
        # Verification_result informing about the error is sent to the work queue.
        if completed_process.returncode != 0:
            verification_result.delay(
                subtask_id,
                VerificationResult.ERROR,
                str(completed_process.stderr),
                'verifier.blender_verification_order.running_blender'
            )
            return
    except SubprocessError as e:
        verification_result.delay(
            subtask_id,
            VerificationResult.ERROR,
            str(e),
            'verifier.blender_verification_order.running_blender'
        )
        return

    # Verifier deletes source files of the Blender project from its storage.
    # At this point there must be source files in VERIFIER_STORAGE_PATH otherwise verification should fail before.
    source_files_list = get_files_list_from_archive(
        os.path.join(settings.VERIFIER_STORAGE_PATH, source_package_path)
    )
    for file_path in source_files_list + [package_paths_to_downloaded_file_names[source_package_path]]:
        delete_file(file_path)

    verification_result.delay(
        subtask_id,
        VerificationResult.MATCH.name,
    )
