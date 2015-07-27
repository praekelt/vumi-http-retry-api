import yaml

from twisted.web import server
from twisted.python import usage
from twisted.application import service, strports

from vumi_http_retry.app import VumiHttpRetryServer


class Options(usage.Options):
    optParameters = [[
        'config', 'c', None,
        'Path to the config file to read from'
    ]]


def makeService(options):
    config = {}

    if options['config'] is not None:
        config = yaml.safe_load(open(options['config']))

    srv = VumiHttpRetryServer(config)
    site = server.Site(srv.app.resource())
    srv_service = service.MultiService()
    strports_service = strports.service(str(srv.config.port), site)
    strports_service.setServiceParent(srv_service)

    return srv_service
