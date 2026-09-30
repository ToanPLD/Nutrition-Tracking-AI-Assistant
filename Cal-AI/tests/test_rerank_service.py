import os
import sys
import unittest
from types import SimpleNamespace

# Ensure Cal-AI root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.services.retrieval.rerank_service import FlashRankService


class TestFlashRankService(unittest.TestCase):

    def setUp(self):
        self.service = FlashRankService.get_instance()

    def test_rerank_hits(self):
        hits = [
            SimpleNamespace(payload={"name": "Bánh xèo miền Tây", "calories": 350}, score=0.6),
            SimpleNamespace(payload={"name": "Phở bò tái", "calories": 400}, score=0.8),
            SimpleNamespace(payload={"name": "Chè đậu xanh", "calories": 250}, score=0.4),
        ]
        reranked = self.service.rerank_hits("phở bò", hits, top_k=2)
        self.assertEqual(len(reranked), 2)
        # "Phở bò tái" should be top 1
        top_name = reranked[0].payload.get("name")
        self.assertEqual(top_name, "Phở bò tái")


if __name__ == "__main__":
    unittest.main()
