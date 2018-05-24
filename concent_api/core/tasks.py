import logging

from celery import shared_task


logger = logging.getLogger(__name__)


@shared_task
def upload_finished(subtask_id: str):  # pylint: disable=unused-argument
    pass
