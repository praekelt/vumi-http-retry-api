from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.tests.utils import ManualWritable
from vumi_http_retry.limiter import TaskLimiter


class TestTaskLimiter(TestCase):
    @inlineCallbacks
    def test_add(self):
        limiter = TaskLimiter(2)
        w = ManualWritable()

        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [])

        yield limiter.add(w.write, 1)
        self.assertEqual(w.writing, [1])
        self.assertEqual(w.written, [])

        yield limiter.add(w.write, 2)
        self.assertEqual(w.writing, [1, 2])
        self.assertEqual(w.written, [])

        d3 = limiter.add(w.write, 3)
        self.assertEqual(w.writing, [1, 2])
        self.assertEqual(w.written, [])

        d4 = limiter.add(w.write, 4)
        self.assertEqual(w.writing, [1, 2])
        self.assertEqual(w.written, [])

        self.assertFalse(d3.called)
        yield w.next()
        yield d3
        self.assertEqual(w.writing, [2, 3])
        self.assertEqual(w.written, [1])

        self.assertFalse(d4.called)
        yield w.next()
        yield d4
        self.assertEqual(w.writing, [3, 4])
        self.assertEqual(w.written, [1, 2])

        yield w.next()
        self.assertEqual(w.writing, [4])
        self.assertEqual(w.written, [1, 2, 3])

        yield w.next()
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [1, 2, 3, 4])

    @inlineCallbacks
    def test_add_err(self):
        errs = []
        w = ManualWritable()
        limiter = TaskLimiter(2, lambda f: errs.append(f.value))

        e1, e2, e4 = [Exception() for i in range(3)]
        yield limiter.add(w.write, 1)
        yield limiter.add(w.write, 2)
        d3 = limiter.add(w.write, 3)
        d4 = limiter.add(w.write, 4)

        self.assertFalse(d3.called)
        self.assertFalse(d4.called)
        self.assertEqual(errs, [])
        self.assertEqual(w.writing, [1, 2])
        self.assertEqual(w.written, [])

        yield w.err(e1)
        yield d3
        self.assertEqual(errs, [e1])
        self.assertEqual(w.writing, [2, 3])
        self.assertEqual(w.written, [])

        yield w.err(e2)
        yield d4
        self.assertEqual(errs, [e1, e2])
        self.assertEqual(w.writing, [3, 4])
        self.assertEqual(w.written, [])

        yield w.next()
        self.assertEqual(w.writing, [4])
        self.assertEqual(w.written, [3])

        yield w.err(e4)
        self.assertEqual(errs, [e1, e2, e4])
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [3])

    @inlineCallbacks
    def test_done(self):
        limiter = TaskLimiter(2)
        w = ManualWritable()

        limiter.add(w.write, 1)
        limiter.add(w.write, 2)
        limiter.add(w.write, 3)
        limiter.add(w.write, 4)

        d = limiter.done()
        self.assertFalse(d.called)
        self.assertEqual(w.writing, [1, 2])
        self.assertEqual(w.written, [])

        yield w.next()
        self.assertFalse(d.called)
        self.assertEqual(w.writing, [2, 3])
        self.assertEqual(w.written, [1])

        yield w.next()
        self.assertFalse(d.called)
        self.assertEqual(w.writing, [3, 4])
        self.assertEqual(w.written, [1, 2])

        yield w.next()
        self.assertFalse(d.called)
        self.assertEqual(w.writing, [4])
        self.assertEqual(w.written, [1, 2, 3])

        yield w.next()
        self.assertTrue(d.called)
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [1, 2, 3, 4])

    @inlineCallbacks
    def test_done_err(self):
        limiter = TaskLimiter(2)
        w = ManualWritable()

        limiter.add(w.write, 1)
        limiter.add(w.write, 2)
        limiter.add(w.write, 3)
        limiter.add(w.write, 4)

        d = limiter.done()
        self.assertFalse(d.called)
        self.assertEqual(w.writing, [1, 2])
        self.assertEqual(w.written, [])

        yield w.err(Exception())
        self.assertFalse(d.called)
        self.assertEqual(w.writing, [2, 3])
        self.assertEqual(w.written, [])

        yield w.err(Exception())
        self.assertFalse(d.called)
        self.assertEqual(w.writing, [3, 4])
        self.assertEqual(w.written, [])

        yield w.next()
        self.assertFalse(d.called)
        self.assertEqual(w.writing, [4])
        self.assertEqual(w.written, [3])

        yield w.err(Exception())
        self.assertTrue(d.called)
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [3])
