from twisted.web.server import Site
from twisted.application import strports

from vumi_http_retry.service import BaseOptions, BaseService
from vumi_http_retry.workers.api.worker import RetryApiWorker


class Options(BaseOptions):
    pass


class Service(BaseService):
    WORKER_CLS = RetryApiWorker


def makeService(options):
    service = Service.from_options(options)
    site = Site(service.worker.app.resource())

    strports_service = strports.service(
        'tcp:{}'.format(str(service.worker.config.port)), site)
    strports_service.setServiceParent(service)

    return service
