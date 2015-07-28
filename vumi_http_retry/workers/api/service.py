import yaml

from twisted.web import server
from twisted.python import usage
from twisted.application import service, strports

from vumi_http_retry.workers.api.worker import VumiHttpRetryApi


class Options(usage.Options):
    optParameters = [[
        'config', 'c', None,
        'Path to the config file to read from'
    ]]


def makeService(options):
    config = {}

    if options['config'] is not None:
        config = yaml.safe_load(open(options['config']))

    api = VumiHttpRetryApi(config)
    site = server.Site(api.app.resource())
    api_service = service.MultiService()
    strports_service = strports.service(str(api.config.port), site)
    strports_service.setServiceParent(api_service)

    return api_service
