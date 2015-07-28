from confmodel import Config
from confmodel.fields import ConfigText

from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.worker import BaseWorker
from vumi_http_retry.service import BaseService


class ToyWorkerConfig(Config):
    filename = ConfigText("The config filename", default='none.yaml')


class ToyWorker(BaseWorker):
    CONFIG_CLS = ToyWorkerConfig

    def __init__(self, config):
        super(ToyWorker, self).__init__(config)
        self.setup_done = False
        self.teardown_done = False

    def setup(self):
        self.setup_done = True

    def teardown(self):
        self.teardown_done = True


class ToyService(BaseService):
    WORKER_CLS = ToyWorker

    @classmethod
    def load_config(cls, filename):
        return {'filename': filename}


class TestBaseService(TestCase):
    def test_from_options(self):
        service = ToyService.from_options({'config': 'foo.yaml'})
        self.assertEqual(service.worker.config.filename, 'foo.yaml')

    def test_from_options_no_config(self):
        service = ToyService.from_options({'config': None})
        self.assertEqual(service.worker.config.filename, 'none.yaml')

    @inlineCallbacks
    def test_start_service(self):
        service = ToyService({'filename': 'foo.yaml'})
        self.assertFalse(service.worker.setup_done)
        yield service.startService()
        self.assertTrue(service.worker.setup_done)

    @inlineCallbacks
    def test_stop_service(self):
        service = ToyService({'filename': 'foo.yaml'})
        self.assertFalse(service.worker.teardown_done)
        yield service.stopService()
        self.assertTrue(service.worker.teardown_done)
