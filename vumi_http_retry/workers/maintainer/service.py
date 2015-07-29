from vumi_http_retry.service import BaseOptions, BaseService
from vumi_http_retry.workers.maintainer.worker import RetryMaintainerWorker


class Options(BaseOptions):
    pass


class Service(BaseService):
    WORKER_CLS = RetryMaintainerWorker


def makeService(options):
    return Service.from_options(options)
