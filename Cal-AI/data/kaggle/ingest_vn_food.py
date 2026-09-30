import csv
import pathlib

from core.services.retrieval.qdrant_service import QdrantService
from core.services.cache.embedding_cache import EmbeddingCache
from core.services.cache.dedup_service import DedupService
from core.embedding.text_embedding_service import TextEmbeddingService

# CSV path: repo_root/backend/data/dataFoodVietNam.csv
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
CSV_PATH = _REPO_ROOT / "backend" / "data" / "dataFoodVietNam.csv"

COLLECTION = "vn_food_vectors_768"
DOMAIN = "food"
SOURCE = "vietnamese_nutrition_database"
SERVING_SIZE = "100g"

EMBED_BATCH = 64
UPSERT_BATCH = 64

_COL_MAP = {
    "TÊN THỨC ĂN":         "food_name",
    "Calories (kcal)":     "calories",
    "Protein (g)":         "protein",
    "Fat (g)":             "fat",
    "Carbonhydrates (g)":  "carbs",
    "Chất xơ (g)":         "fiber",
    "Cholesterol (mg)":    "cholesterol",
    "Canxi (mg)":          "calcium",
    "Photpho (mg)":        "phosphorus",
    "Sắt (mg)":            "iron",
    "Natri (mg)":          "sodium",
    "Kali (mg)":           "potassium",
    "Beta Caroten (mcg)":  "beta_carotene",
    "Vitamin A (mcg)":     "vitamin_a",
    "Vitamin B1 (mg)":     "vitamin_b1",
    "Vitamin C (mg)":      "vitamin_c",
    "Loại":                "category",
}


def _parse_vn_number(raw: str):
    """Convert Vietnamese decimal string (e.g. '8,6' or '1.5') to float."""
    cleaned = raw.strip().replace(",", ".") if raw else ""
    # strip trailing non-numeric chars like 'g'
    cleaned = "".join(c for c in cleaned if c in "0123456789.")
    try:
        return float(cleaned) if cleaned else 0.0
    except ValueError:
        return 0.0


def _load_csv():
    rows = []
    with open(CSV_PATH, encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            record: dict = {}
            for csv_col, field in _COL_MAP.items():
                val = raw.get(csv_col, "").strip()
                if field == "food_name" or field == "category":
                    record[field] = val
                else:
                    record[field] = _parse_vn_number(val)
            record["serving_size"] = SERVING_SIZE
            record["domain"] = DOMAIN
            record["source"] = SOURCE
            record["language"] = "vi"
            rows.append(record)
    return rows


def _build_text(r: dict) -> str:
    """Build a rich bilingual text for semantic embedding."""
    parts = [r["food_name"]]
    if r.get("category"):
        parts.append(f"Loại: {r['category']}")
    if r.get("calories"):
        parts.append(f"Calo: {r['calories']} kcal")
    if r.get("protein"):
        parts.append(f"Protein: {r['protein']}g")
    if r.get("fat"):
        parts.append(f"Chất béo: {r['fat']}g")
    if r.get("carbs"):
        parts.append(f"Carbs: {r['carbs']}g")
    if r.get("fiber"):
        parts.append(f"Chất xơ: {r['fiber']}g")
    if r.get("sodium"):
        parts.append(f"Natri: {r['sodium']}mg")
    if r.get("calcium"):
        parts.append(f"Canxi: {r['calcium']}mg")
    if r.get("iron"):
        parts.append(f"Sắt: {r['iron']}mg")
    if r.get("vitamin_c"):
        parts.append(f"Vitamin C: {r['vitamin_c']}mg")
    parts.append("nguồn: cơ sở dữ liệu dinh dưỡng Việt Nam")
    return " | ".join(parts)[:400]


def run():
    print("[INFO] ingest_vn_food - Vietnamese Nutrition Database (768-dim)")
    print(f"[INFO] CSV: {CSV_PATH}")

    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}")

    records = _load_csv()
    print(f"[INFO] Loaded {len(records)} rows")

    qdrant = QdrantService()
    text_embed = TextEmbeddingService()
    cache = EmbeddingCache()
    dedup = DedupService()

    batch: list[dict] = []
    texts: list[str] = []
    payloads: list[dict] = []
    total = 0

    for record in records:
        if not record.get("food_name"):
            continue

        if dedup.is_duplicate(record):
            continue

        text = _build_text(record)
        cache_key = f"mpnet768:vn:{text}"
        cached = cache.get(cache_key)

        if cached:
            batch.append({"vector": cached, "payload": record})
            total += 1
        else:
            texts.append(text)
            payloads.append(record)

        if len(texts) >= EMBED_BATCH:
            vectors = text_embed.embed_batch(texts)
            for t, p, v in zip(texts, payloads, vectors):
                if v is None:
                    continue
                cache.set(f"mpnet768:vn:{t}", v)
                batch.append({"vector": v, "payload": p})
                total += 1
            texts.clear()
            payloads.clear()

        if len(batch) >= UPSERT_BATCH:
            qdrant.upsert_generic(COLLECTION, batch)
            print(f"  [OK] Upserted: {total}")
            batch.clear()

    # flush remaining texts
    if texts:
        vectors = text_embed.embed_batch(texts)
        for t, p, v in zip(texts, payloads, vectors):
            if v is None:
                continue
            cache.set(f"mpnet768:vn:{t}", v)
            batch.append({"vector": v, "payload": p})
            total += 1

    if batch:
        qdrant.upsert_generic(COLLECTION, batch)

    print(f"\n[DONE] ingest_vn_food -> {total} records in '{COLLECTION}'")


if __name__ == "__main__":
    run()
