from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.tests.utils import ManualReadable, ManualWritable
from vumi_http_retry.utils import run_concurrently


class TestRunConcurrently(TestCase):
    @inlineCallbacks
    def test_concurrency(self):
        source = ManualReadable([i for i in range(4)])
        target = ManualWritable()

        d = run_concurrently(2, source.read, target.write)
        self.assertEqual(source.unread, [1, 2, 3])
        self.assertEqual(source.reading, [0])
        self.assertEqual(target.writing, [])
        self.assertEqual(target.written, [])

        yield source.next()
        self.assertEqual(source.unread, [2, 3])
        self.assertEqual(source.reading, [1])
        self.assertEqual(target.writing, [0])
        self.assertEqual(target.written, [])

        yield source.next()
        self.assertEqual(source.unread, [2, 3])
        self.assertEqual(source.reading, [])
        self.assertEqual(target.writing, [0, 1])
        self.assertEqual(target.written, [])

        yield target.next()
        self.assertEqual(source.unread, [3])
        self.assertEqual(source.reading, [2])
        self.assertEqual(target.writing, [1])
        self.assertEqual(target.written, [0])

        yield target.next()
        self.assertEqual(source.unread, [3])
        self.assertEqual(source.reading, [2])
        self.assertEqual(target.writing, [])
        self.assertEqual(target.written, [0, 1])

        yield source.next()
        self.assertEqual(source.unread, [])
        self.assertEqual(source.reading, [3])
        self.assertEqual(target.writing, [2])
        self.assertEqual(target.written, [0, 1])

        yield target.next()
        self.assertEqual(source.unread, [])
        self.assertEqual(source.reading, [3])
        self.assertEqual(target.writing, [])
        self.assertEqual(target.written, [0, 1, 2])

        yield source.next()
        self.assertEqual(source.unread, [])
        self.assertEqual(source.reading, [])
        self.assertEqual(target.writing, [3])
        self.assertEqual(target.written, [0, 1, 2])

        yield target.next()
        self.assertEqual(source.unread, [])
        self.assertEqual(source.reading, [])
        self.assertEqual(target.writing, [])
        self.assertEqual(target.written, [0, 1, 2, 3])

        yield d

    @inlineCallbacks
    def test_next_errback(self):
        source = ManualReadable([i for i in range(4)])
        target = ManualWritable()

        e = Exception()
        errs = []

        run_concurrently(
            2, source.read, target.write,
            errback=(lambda f: errs.append(f.value)))

        self.assertEqual(source.unread, [1, 2, 3])
        self.assertEqual(source.reading, [0])
        self.assertEqual(target.writing, [])
        self.assertEqual(target.written, [])

        self.assertEqual(errs, [])
        yield source.err(e)
        self.assertEqual(errs, [e])

    @inlineCallbacks
    def test_run_errback(self):
        source = ManualReadable([i for i in range(4)])
        target = ManualWritable()

        e = Exception()
        errs = []

        run_concurrently(
            2, source.read, target.write,
            errback=(lambda f: errs.append(f.value)))

        yield source.next()
        self.assertEqual(source.unread, [2, 3])
        self.assertEqual(source.reading, [1])
        self.assertEqual(target.writing, [0])
        self.assertEqual(target.written, [])

        self.assertEqual(errs, [])
        yield target.err(e)
        self.assertEqual(errs, [e])
