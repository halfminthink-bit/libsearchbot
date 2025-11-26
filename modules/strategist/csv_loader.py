"""
CSV ローダー
ターゲット書籍リスト（ISBN, 地域ID等）をCSVから読み込む
"""

import csv
import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class TargetBook:
    """ターゲット書籍を格納するデータクラス"""
    isbn: str
    region_id: str
    keyword_suffix: str = "図書館"

    def __post_init__(self):
        """ISBNからハイフンを除去"""
        self.isbn = self.isbn.replace("-", "")


class CSVLoader:
    """CSVファイルからターゲット書籍を読み込むクラス"""

    REQUIRED_COLUMNS = ["isbn", "region_id"]
    DEFAULT_KEYWORD_SUFFIX = "図書館"

    def __init__(self, filepath: str):
        """
        Args:
            filepath: CSVファイルのパス
        """
        self.filepath = filepath

    def load(self) -> list[TargetBook]:
        """
        CSVファイルを読み込み、TargetBookのリストを返す

        Returns:
            list[TargetBook]: ターゲット書籍のリスト

        Raises:
            FileNotFoundError: ファイルが見つからない場合
            ValueError: 必須カラムがない場合
        """
        if not os.path.exists(self.filepath):
            raise FileNotFoundError(f"CSV file not found: {self.filepath}")

        targets = []

        with open(self.filepath, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # 必須カラムの確認
            if reader.fieldnames is None:
                raise ValueError("CSV file is empty or has no header")

            missing_columns = [col for col in self.REQUIRED_COLUMNS if col not in reader.fieldnames]
            if missing_columns:
                raise ValueError(f"Missing required columns: {missing_columns}")

            # データの読み込み
            for row_num, row in enumerate(reader, start=2):  # ヘッダー行を1とする
                isbn = row.get("isbn", "").strip()
                region_id = row.get("region_id", "").strip()

                # 空行やISBNが空の場合はスキップ
                if not isbn:
                    print(f"  Warning: Row {row_num} has empty ISBN, skipping")
                    continue

                if not region_id:
                    print(f"  Warning: Row {row_num} has empty region_id, skipping")
                    continue

                # オプションカラム
                keyword_suffix = row.get("keyword_suffix", "").strip()
                if not keyword_suffix:
                    keyword_suffix = self.DEFAULT_KEYWORD_SUFFIX

                targets.append(TargetBook(
                    isbn=isbn,
                    region_id=region_id,
                    keyword_suffix=keyword_suffix
                ))

        return targets

    def load_as_dicts(self) -> list[dict]:
        """
        CSVファイルを読み込み、辞書のリストを返す

        Returns:
            list[dict]: 辞書のリスト
        """
        targets = self.load()
        return [
            {
                "isbn": t.isbn,
                "region_id": t.region_id,
                "keyword_suffix": t.keyword_suffix
            }
            for t in targets
        ]


# 単体テスト用
if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

    # テスト用CSVのパス
    csv_path = "data/input/target_books.csv"

    print(f"Testing CSVLoader with: {csv_path}")
    print("-" * 50)

    try:
        loader = CSVLoader(csv_path)
        targets = loader.load()

        print(f"Loaded {len(targets)} targets:")
        for i, target in enumerate(targets, start=1):
            print(f"  {i}. ISBN: {target.isbn}, Region: {target.region_id}, Keyword: {target.keyword_suffix}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
    except ValueError as e:
        print(f"Error: {e}")
