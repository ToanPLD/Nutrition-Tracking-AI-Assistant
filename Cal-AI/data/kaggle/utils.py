# data/kaggle/utils.py

import csv
import os
from io import StringIO

try:
    import pandas as pd
except Exception:
    pd = None


class RowDict(dict):
    def to_dict(self):
        return dict(self)


class SimpleDataFrame:
    def __init__(self, records):
        self.records = records

    def __len__(self):
        return len(self.records)

    def iterrows(self):
        for idx, rec in enumerate(self.records):
            yield idx, RowDict(rec)


def find_all_csv_files(dataset_path):
    csv_files = []

    for root, _, files in os.walk(dataset_path):
        for f in files:
            if f.lower().endswith(".csv"):
                csv_files.append(os.path.join(root, f))

    print(f"[INFO] Found {len(csv_files)} CSV files")
    return csv_files


def load_csv_safe(file_path):
    print(f"[INFO] Loading: {file_path}")

    if pd is not None:
        try:
            df = pd.read_csv(
                file_path,
                encoding="utf-8",
                on_bad_lines="skip",
                low_memory=False
            )
            df = df.loc[:, ~df.columns.str.contains("^Unnamed")]
            df.columns = df.columns.str.strip()
            df = df.dropna(how="all")
            for col in df.columns:
                if df[col].dtype == "object":
                    df[col] = df[col].fillna("").astype(str)
                else:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            print(f"[INFO] Loaded with pandas: {len(df)} rows")
            return df
        except Exception as e:
            print(f"[WARN] pandas read_csv failed ({e}), falling back to built-in csv reader")

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            records = []
            for row in reader:
                clean_row = {
                    k.strip(): v.strip() if isinstance(v, str) else v
                    for k, v in row.items()
                    if k and not k.strip().startswith("Unnamed")
                }
                if any(clean_row.values()):
                    records.append(clean_row)
            print(f"[INFO] Loaded with standard csv: {len(records)} rows")
            return SimpleDataFrame(records)
    except Exception as e:
        print(f"[ERROR] Failed to load {file_path}: {e}")
        return None
