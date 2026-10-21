import io
import json
import unittest
from unittest.mock import patch
from etl.validate_release import http_benchmark

class ReleaseValidationTests(unittest.TestCase):
    def test_http_benchmark_encodes_chinese_filters(self):
        visited=[]
        def response(url,timeout):
            self.assertTrue(url.isascii())
            self.assertEqual(timeout,15)
            visited.append(url)
            return io.BytesIO(json.dumps({'total':7}).encode())
        with patch('etl.validate_release.urlopen',side_effect=response):
            results=http_benchmark('http://127.0.0.1:5001',10,2)
        self.assertEqual(len(results),4)
        self.assertTrue(any('level=%E4%B8%89%E7%94%B2' in url for url in visited))
        self.assertTrue(all(r['total']==7 and r['samples']==10 for r in results))

if __name__=='__main__':unittest.main()
