from twisted.web import server
from twisted.python import usage
from twisted.application import service, strports

from vumi_http_retry.app import VumiHttpRetryServer


class Options(usage.Options):
    optParameters = [[
        'port', 'p', '8080',
        'Port to listen on'
    ]]


def makeService(options):
    server = VumiHttpRetryServer()

    site = server.Site(server.app.resource())
    srv_service = service.MultiService()
    strports_service = strports.service(options['port'], site)
    strports_service.setServiceParent(srv_service)

    return srv_service
