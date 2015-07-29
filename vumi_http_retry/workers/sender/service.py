from vumi_http_retry.service import BaseOptions, BaseService
from vumi_http_retry.workers.sender.worker import RetrySenderWorker


class Options(BaseOptions):
    pass


class Service(BaseService):
    WORKER_CLS = RetrySenderWorker


def makeService(options):
    return Service.from_options(options)
