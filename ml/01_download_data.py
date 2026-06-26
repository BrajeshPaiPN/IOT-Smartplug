"""
Smart Solar Plug — Dataset Downloader
Downloads real solar plant datasets from Kaggle using the Kaggle API.

TRAINING dataset : anikannal/solar-power-generation-data  (India, 2020, 34 days)
TESTING  dataset : biswajitdas/solar-power-dataset-kerala-2019-to-2024

Requirements:
  pip install kaggle
  Place your kaggle.json in ~/.kaggle/kaggle.json  (or set KAGGLE_USERNAME + KAGGLE_KEY env vars)
"""

import os
import sys
import zipfile
import shutil
from pathlib import Path

# Project root
ROOT = Path(__file__).parent.parent
TRAIN_DIR = ROOT / "data" / "training"
TEST_DIR  = ROOT / "data" / "testing"

TRAIN_DATASET = "anikannal/solar-power-generation-data"
TEST_DATASET  = "biswajitdas/solar-power-dataset-kerala-2019-to-2024"


def check_kaggle_auth():
    """Verify Kaggle credentials are available."""
    kaggle_json = Path.home() / ".kaggle" / "kaggle.json"
    has_env = os.environ.get("KAGGLE_USERNAME") and os.environ.get("KAGGLE_KEY")
    has_file = kaggle_json.exists()
    if not has_env and not has_file:
        print("\n" + "="*70)
        print("  KAGGLE CREDENTIALS NOT FOUND")
        print("="*70)
        print("""
To download datasets automatically:

Option A — Use kaggle.json:
  1. Go to https://www.kaggle.com → Account → Create API Token
  2. Place the downloaded kaggle.json at: ~/.kaggle/kaggle.json
  3. Re-run this script

Option B — Set environment variables:
  set KAGGLE_USERNAME=your_username
  set KAGGLE_KEY=your_api_key

Option C — Manual Download (NO login script needed):
  TRAINING SET:
    URL: https://www.kaggle.com/datasets/anikannal/solar-power-generation-data
    Download ZIP → extract all CSVs into:
    data/training/

  TESTING SET:
    URL: https://www.kaggle.com/datasets/biswajitdas/solar-power-dataset-kerala-2019-to-2024
    Download ZIP → extract all CSVs into:
    data/testing/

  Required files in data/training/:
    - Plant_1_Generation_Data.csv
    - Plant_1_Weather_Sensor_Data.csv

  Required files in data/testing/:
    - solar_data.csv  (or any CSV from the Kerala dataset)
""")
        return False
    return True


def download_dataset(dataset_slug: str, dest_dir: Path):
    """Download and extract a Kaggle dataset."""
    import kaggle  # noqa: imported after auth check

    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n[+] Downloading: {dataset_slug}")
    print(f"    Destination : {dest_dir}")

    kaggle.api.authenticate()
    kaggle.api.dataset_download_files(
        dataset_slug,
        path=str(dest_dir),
        unzip=True,
        quiet=False,
    )
    print(f"[✓] Downloaded & extracted: {dataset_slug}")


def verify_training_files():
    """Check that required training CSVs are present."""
    required = [
        "Plant_1_Generation_Data.csv",
        "Plant_1_Weather_Sensor_Data.csv",
    ]
    missing = [f for f in required if not (TRAIN_DIR / f).exists()]
    if missing:
        print(f"\n[!] Missing training files: {missing}")
        print(f"    Expected in: {TRAIN_DIR}")
        return False
    print(f"[✓] Training files verified in {TRAIN_DIR}")
    return True


def verify_testing_files():
    """Check at least one CSV exists in test dir."""
    csvs = list(TEST_DIR.glob("*.csv"))
    if not csvs:
        print(f"\n[!] No CSV files found in testing dir: {TEST_DIR}")
        return False
    print(f"[✓] Testing files found: {[f.name for f in csvs]}")
    return True


def main():
    print("=" * 60)
    print("  Smart Solar Plug — Dataset Downloader")
    print("=" * 60)

    # Check if already downloaded
    train_ready = verify_training_files()
    test_ready  = verify_testing_files()

    if train_ready and test_ready:
        print("\n[✓] All datasets already present. Skipping download.")
        return

    # Try Kaggle API
    if not check_kaggle_auth():
        sys.exit(1)

    try:
        if not train_ready:
            download_dataset(TRAIN_DATASET, TRAIN_DIR)
            verify_training_files()

        if not test_ready:
            download_dataset(TEST_DATASET, TEST_DIR)
            verify_testing_files()

    except Exception as exc:
        print(f"\n[ERROR] Download failed: {exc}")
        print("Please use the manual download option described above.")
        sys.exit(1)

    print("\n[✓] All datasets downloaded successfully!")
    print("    Next step: python ml/02_train_cleaning_alert_model.py")


if __name__ == "__main__":
    main()
