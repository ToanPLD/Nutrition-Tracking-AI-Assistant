import asyncio
import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

# Ensure Cal-AI root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.services.retrieval.rerank_service import FlashRankService
from core.services.llm.llm_service import LLMService
from api.routes.agentic_rag import AgenticQueryRequest, _resolve_context, _enrich_response


class TestRetrievalBenchmarkAndStreaming(unittest.TestCase):

    def setUp(self):
        self.rerank_service = FlashRankService.get_instance()
        self.llm_service = LLMService()

    def test_benchmark_vietnamese_food_reranking_accuracy(self):
        """Task 5.1: Benchmark cross-encoder reranker on Vietnamese food queries."""
        # Scenario: Raw vector retrieval had false positive scores due to general semantic proximity
        # Query 1: "phở bò tái chín"
        candidates_pho = [
            SimpleNamespace(payload={"name": "Cơm tấm sườn bì chả", "calories": 650, "protein": 28}, score=0.78),
            SimpleNamespace(payload={"name": "Phở bò Hà Nội truyền thống", "calories": 450, "protein": 32}, score=0.69),
            SimpleNamespace(payload={"name": "Bún chả nem cua bể", "calories": 520, "protein": 24}, score=0.74),
            SimpleNamespace(payload={"name": "Canh khổ qua nhồi thịt", "calories": 180, "protein": 12}, score=0.61),
        ]
        # Without FlashRank: Rank 1 is "Cơm tấm sườn bì chả" (score=0.78)
        self.assertEqual(candidates_pho[0].payload["name"], "Cơm tấm sườn bì chả")

        # With FlashRank:
        reranked_pho = self.rerank_service.rerank_hits("phở bò tái chín", candidates_pho, top_k=2)
        self.assertEqual(len(reranked_pho), 2)
        self.assertEqual(reranked_pho[0].payload["name"], "Phở bò Hà Nội truyền thống")

        # Query 2: "ức gà luộc giảm cân"
        candidates_ga = [
            SimpleNamespace(payload={"name": "Gà rán giòn sốt cay", "calories": 580, "fat": 35}, score=0.75),
            SimpleNamespace(payload={"name": "Ức gà hấp sả phi lê", "calories": 165, "protein": 31}, score=0.65),
            SimpleNamespace(payload={"name": "Chân gà ngâm sả tắc", "calories": 300, "fat": 18}, score=0.72),
        ]
        reranked_ga = self.rerank_service.rerank_hits("ức gà luộc giảm cân", candidates_ga, top_k=1)
        self.assertEqual(reranked_ga[0].payload["name"], "Ức gà hấp sả phi lê")

    def test_streaming_token_latency_and_ttft(self):
        """Task 5.2: Verify Time-To-First-Token and chunk streaming delivery."""
        async def run_stream_test():
            # Mock AsyncOpenAI chat completions create stream
            mock_chunks = [
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="Để "))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="giảm "))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="cân "))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="hiệu "))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="quả, "))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="bạn "))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="nên "))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="duy trì "))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="thâm hụt "))]),
                SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content="calo."))]),
            ]

            async def mock_chunk_generator():
                for c in mock_chunks:
                    await asyncio.sleep(0.01)  # 10ms network chunk simulation
                    yield c

            mock_client = MagicMock()
            mock_client.chat.completions.create = AsyncMock(return_value=mock_chunk_generator())
            self.llm_service._openai_client = mock_client
            self.llm_service.backend = "openai"

            start_time = time.perf_counter()
            first_token_time = None
            received_tokens = []

            async for token in self.llm_service.stream_openai_chat("Tư vấn giảm cân"):
                if first_token_time is None:
                    first_token_time = time.perf_counter() - start_time
                received_tokens.append(token)

            total_time = time.perf_counter() - start_time
            full_response = "".join(received_tokens)

            # Assertions
            self.assertIsNotNone(first_token_time)
            # Verify TTFT is well under 500ms
            self.assertLess(first_token_time, 0.5, f"TTFT was {first_token_time * 1000:.1f}ms (expected < 500ms)")
            self.assertEqual(len(received_tokens), 10)
            self.assertEqual(full_response, "Để giảm cân hiệu quả, bạn nên duy trì thâm hụt calo.")

        asyncio.run(run_stream_test())

    def test_agentic_query_request_and_context_resolution(self):
        """Verify request compatibility for question vs query and conversation context formatting."""
        # 1. Payload with 'question'
        req1 = AgenticQueryRequest(question="Bún bò Huế bao nhiêu calo?")
        self.assertEqual(req1.final_query, "Bún bò Huế bao nhiêu calo?")

        # 2. Payload with 'query' (as sent by backend Express proxy)
        req2 = AgenticQueryRequest(query="1 quả chuối bao nhiêu calo?")
        self.assertEqual(req2.final_query, "1 quả chuối bao nhiêu calo?")

        # 3. Payload with history list
        req3 = AgenticQueryRequest(
            query="Còn món này thì sao?",
            history=[
                {"sender": "user", "text": "Trưa nay ăn cơm sườn"},
                {"sender": "ai", "text": "Cơm sườn có khoảng 600 calo."}
            ]
        )
        resolved_ctx = _resolve_context(req3)
        self.assertIn("user: Trưa nay ăn cơm sườn", resolved_ctx)
        self.assertIn("ai: Cơm sườn có khoảng 600 calo.", resolved_ctx)

        # 4. Enrich response with backward compatible aliases
        res = _enrich_response({"answer": "Phở bò có khoảng 450 kcal."})
        self.assertEqual(res["response"], "Phở bò có khoảng 450 kcal.")
        self.assertEqual(res["text"], "Phở bò có khoảng 450 kcal.")


if __name__ == "__main__":
    unittest.main()
