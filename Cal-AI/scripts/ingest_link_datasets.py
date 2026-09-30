#!/usr/bin/env python3
"""
Ingest all link datasets into Qdrant Cloud cluster.

Datasets:
1. Vietnamese Food (backend/data/dataFoodVietNam.csv) -> vn_food_vectors_768
2. Starbucks Drinks (henryshan/starbucks) -> beverage_vectors_768
3. Gym Members Exercise (valakhorasani/gym-members-exercise-dataset) -> exercise_gym_vectors_768
4. Calories Burned (jockeroika/calories-burned) -> exercise_text_vectors_768
5. Obesity Levels (fatemehmehrparvar/obesity-levels) -> lifestyle_obesity_vectors_768
6. Life Style Data (jockeroika/life-style-data) -> lifestyle_vectors_768
7. Beverage Caffeine (heitornunes/caffeine-content-of-drinks) -> beverage_text_vectors_768
8. Nutritional Content of Food (thedevastator/the-nutritional-content-of-food-a-comprehensive) -> food_nutrition_dev_vectors_768
"""

import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.services.retrieval.qdrant_service import QdrantService


def get_existing_counts(qdrant: QdrantService) -> dict[str, int]:
    counts = {}
    for col in qdrant.available_collections():
        try:
            cnt = qdrant.client.count(col, exact=False).count
            counts[col] = cnt
        except Exception:
            counts[col] = 0
    return counts


def main():
    print("=" * 80)
    print("[PIPELINE] Ingesting Datasets to Qdrant Cloud")
    print("=" * 80)

    qdrant = QdrantService()
    counts = get_existing_counts(qdrant)
    print(f"[INFO] Current Collections in Qdrant: {counts}")

    # 1. VN Food
    if counts.get("vn_food_vectors_768", 0) >= 100:
        print("[SKIP] vn_food_vectors_768 already populated (count=%d)" % counts["vn_food_vectors_768"])
    else:
        print("\n--- Ingesting Vietnamese Food ---")
        try:
            from data.kaggle.ingest_vn_food import run as run_vn
            run_vn()
        except Exception as e:
            print("[ERROR] Failed to ingest VN Food:", e)

    # 2. Starbucks Drinks
    if counts.get("beverage_vectors_768", 0) >= 200:
        print("[SKIP] beverage_vectors_768 already populated (count=%d)" % counts["beverage_vectors_768"])
    else:
        print("\n--- Ingesting Starbucks Drinks ---")
        try:
            from data.kaggle.ingest_starbucks import run as run_sb
            run_sb()
        except Exception as e:
            print("[ERROR] Failed to ingest Starbucks:", e)

    # 3. Gym Exercise
    if counts.get("exercise_gym_vectors_768", 0) >= 800:
        print("[SKIP] exercise_gym_vectors_768 already populated (count=%d)" % counts["exercise_gym_vectors_768"])
    else:
        print("\n--- Ingesting Gym Exercise Tracking ---")
        try:
            from data.kaggle.ingest_gym import run as run_gym
            run_gym()
        except Exception as e:
            print("[ERROR] Failed to ingest Gym:", e)

    # 4. Calories Burned
    if counts.get("exercise_text_vectors_768", 0) >= 100:
        print("[SKIP] exercise_text_vectors_768 already populated (count=%d)" % counts["exercise_text_vectors_768"])
    else:
        print("\n--- Ingesting Calories Burned ---")
        try:
            from data.kaggle.ingest_calories_burned import run as run_cal
            run_cal()
        except Exception as e:
            print("[ERROR] Failed to ingest Calories Burned:", e)

    # 5. Lifestyle Obesity
    if counts.get("lifestyle_obesity_vectors_768", 0) >= 500:
        print("[SKIP] lifestyle_obesity_vectors_768 already populated (count=%d)" % counts["lifestyle_obesity_vectors_768"])
    else:
        print("\n--- Ingesting Obesity Levels ---")
        try:
            from data.kaggle.ingest_obesity_lifestyle import run as run_ob
            run_ob()
        except Exception as e:
            print("[ERROR] Failed to ingest Obesity Levels:", e)

    # 6. Lifestyle Data
    if counts.get("lifestyle_vectors_768", 0) >= 200:
        print("[SKIP] lifestyle_vectors_768 already populated (count=%d)" % counts["lifestyle_vectors_768"])
    else:
        print("\n--- Ingesting Life Style Data ---")
        try:
            from data.kaggle.ingest_lifestyle import run as run_ls
            run_ls()
        except Exception as e:
            print("[ERROR] Failed to ingest Lifestyle Data:", e)

    # 7. Beverage Caffeine
    if counts.get("beverage_text_vectors_768", 0) >= 100:
        print("[SKIP] beverage_text_vectors_768 already populated (count=%d)" % counts["beverage_text_vectors_768"])
    else:
        print("\n--- Ingesting Beverage Caffeine ---")
        try:
            from data.kaggle.ingest_beverage import run as run_bev
            run_bev()
        except Exception as e:
            print("[ERROR] Failed to ingest Beverage Caffeine:", e)

    # 8. Food Nutrition Dev
    if counts.get("food_nutrition_dev_vectors_768", 0) >= 1000:
        print("[SKIP] food_nutrition_dev_vectors_768 already populated (count=%d)" % counts["food_nutrition_dev_vectors_768"])
    else:
        print("\n--- Ingesting Food Nutrition Content ---")
        try:
            from data.kaggle.ingest_food_nutrition import run as run_fn
            run_fn()
        except Exception as e:
            print("[ERROR] Failed to ingest Food Nutrition:", e)

    print("\n" + "=" * 80)
    print("[SUMMARY] Dataset Ingestion Complete. Final Collections:")
    final_counts = get_existing_counts(qdrant)
    for col, count in sorted(final_counts.items()):
        print(f"  - {col}: {count} records")
    print("=" * 80)


if __name__ == "__main__":
    main()
