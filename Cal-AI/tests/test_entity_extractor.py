import os
import sys
import unittest

# Ensure Cal-AI root is on sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.agent.entity_extractor import EntityExtractor, normalize_vietnamese


class TestEntityExtractor(unittest.TestCase):

    def test_normalize_vietnamese(self):
        self.assertEqual(normalize_vietnamese("Phở Bò Tái Đỗ"), "pho bo tai do")
        self.assertEqual(normalize_vietnamese("Bánh Xèo Giòn"), "banh xeo gion")

    def test_extract_food_entity_simple(self):
        query = "Cho mình hỏi một tô phở bò có bao nhiêu calo và đạm?"
        entity = EntityExtractor.extract_food_entity(query)
        self.assertIn("pho bo", entity)
        self.assertNotIn("cho minh hoi", entity)
        self.assertNotIn("bao nhieu calo", entity)

    def test_extract_food_entity_noisy(self):
        query = "Bạn ơi tính giúp mình 1 đĩa cơm tấm sườn bì chả bao nhiêu kcal vậy ạ?"
        entity = EntityExtractor.extract_food_entity(query)
        self.assertIn("com tam suon bi cha", entity)
        self.assertNotIn("tinh giup", entity)
        self.assertNotIn("bao nhieu kcal", entity)

    def test_extract_english_title_case(self):
        query = "Cho mình xin thông tin dinh dưỡng của Broiled Salmon Steaks với"
        entity = EntityExtractor.extract_food_entity(query)
        self.assertEqual(entity, "Broiled Salmon Steaks")

    def test_extract_follow_up_anaphora(self):
        history = "User: Mình muốn ăn bún chả Hà Nội\nAssistant: Bún chả có khoảng 450 kcal."
        follow_up = "Vậy món này có nhiều chất béo không?"
        entity = EntityExtractor.extract_food_entity(follow_up, conversation_context=history)
        print("DEBUG ENTITY:", repr(entity))
        self.assertIn("bun cha", entity)

    def test_extract_comparison_entities(self):
        query = "So sánh calo giữa chả giò và bánh xèo"
        terms = EntityExtractor.extract_comparison_entities(query)
        self.assertTrue(any("cha gio" in t for t in terms))
        self.assertTrue(any("banh xeo" in t for t in terms))


if __name__ == "__main__":
    unittest.main()
