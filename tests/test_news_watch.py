import unittest
from cqwe.news_watch import parse


class NewsTests(unittest.TestCase):
    def test_publication_time_does_not_backdate_observation(self):
        raw=b'<rss><channel><item><title>Data</title><link>https://example.com</link><pubDate>Wed, 14 Oct 2026 12:30:00 GMT</pubDate></item></channel></rss>'
        row=parse(raw,'BLS_CPI',2000000000000)[0]
        self.assertEqual(row['available_ms'],2000000000000)
        self.assertLess(row['published_ms'],row['first_seen_ms'])
        self.assertIsNone(row['directional_signal'])

    def test_unknown_timezone_is_not_assumed(self):
        raw=b'<rss><channel><item><title>Data</title><pubDate>invalid</pubDate></item></channel></rss>'
        self.assertIsNone(parse(raw,'SEC',1234)[0]['published_ms'])

    def test_revision_preserves_distinct_identity(self):
        a=parse(b'<rss><item><title>A</title></item></rss>','FED',1)[0]
        b=parse(b'<rss><item><title>B</title></item></rss>','FED',2)[0]
        self.assertNotEqual(a['id'],b['id'])

    def test_source_and_payload_budget(self):
        with self.assertRaises(ValueError):parse(b'<rss/>','UNTRUSTED',0)
        with self.assertRaises(ValueError):parse(b'x'*500001,'FED',0)


if __name__=='__main__':unittest.main()
