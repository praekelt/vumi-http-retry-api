from twisted.trial.unittest import TestCase
from twisted.internet.defer import inlineCallbacks

from vumi_http_retry.tests.utils import ManualReadable, ManualWritable
from vumi_http_retry.utils import run_concurrently


class TestManualReadable(TestCase):
    @inlineCallbacks
    def test_reading(self):
        r = ManualReadable([1, 2, 3, 4])
        self.assertEqual(r.unread, [1, 2, 3, 4])
        self.assertEqual(r.reading, [])

        d1 = r.read()
        self.assertEqual(r.unread, [2, 3, 4])
        self.assertEqual(r.reading, [1])

        d2 = r.read()
        self.assertEqual(r.unread, [3, 4])
        self.assertEqual(r.reading, [1, 2])

        self.assertEqual(d1, r.next())
        self.assertEqual((yield d1), 1)
        self.assertEqual(r.unread, [3, 4])
        self.assertEqual(r.reading, [2])

        self.assertEqual(d2, r.next())
        self.assertEqual((yield d2), 2)
        self.assertEqual(r.unread, [3, 4])
        self.assertEqual(r.reading, [])

        d = r.read()
        self.assertEqual(r.unread, [4])
        self.assertEqual(r.reading, [3])
        self.assertEqual(d, r.next())
        self.assertEqual((yield d), 3)

        d = r.read()
        self.assertEqual(r.unread, [])
        self.assertEqual(r.reading, [4])
        self.assertEqual(d, r.next())
        self.assertEqual((yield d), 4)

        self.assertEqual((yield r.read()), None)
        self.assertEqual((yield r.read()), None)

    def test_next_empty_reading(self):
        r = ManualReadable([23])
        self.assertRaises(Exception, r.next)


class TestManualWritable(TestCase):
    @inlineCallbacks
    def test_reading(self):
        w = ManualWritable()
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [])

        d1 = w.write(1)
        self.assertEqual(w.writing, [1])
        self.assertEqual(w.written, [])

        d2 = w.write(2)
        self.assertEqual(w.writing, [1, 2])
        self.assertEqual(w.written, [])

        self.assertEqual(d1, w.next())
        yield d1
        self.assertEqual(w.writing, [2])
        self.assertEqual(w.written, [1])

        self.assertEqual(d2, w.next())
        yield d2
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [1, 2])

        d = w.write(3)
        self.assertEqual(w.writing, [3])
        self.assertEqual(w.written, [1, 2])
        self.assertEqual(d, w.next())
        yield d
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [1, 2, 3])

        d = w.write(4)
        self.assertEqual(w.writing, [4])
        self.assertEqual(w.written, [1, 2, 3])
        self.assertEqual(d, w.next())
        yield d
        self.assertEqual(w.writing, [])
        self.assertEqual(w.written, [1, 2, 3, 4])

    def test_next_empty_writing(self):
        w = ManualWritable()
        self.assertRaises(Exception, w.next)
