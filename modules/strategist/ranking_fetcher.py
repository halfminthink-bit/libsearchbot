"""
楽天ブックス検索API(売上順)からランキングを取得する
楽天ブックスAPIからランキングを取得し、記事作成対象のISBNリストを生成する
"""

import os
import requests
from typing import List, Optional
from dataclasses import dataclass

from dotenv import load_dotenv
load_dotenv(override=True)


@dataclass
class TargetBook:
    """記事作成対象の書籍情報"""
    isbn: str
    title: str
    genre_id: str
    suggested_region: str  # ジャンルに基づく推奨ターゲット地域


class RankingFetcher:
    """楽天ブックス検索API(売上順)からランキングを取得する"""

    # RankingではなくSearchを使う
    API_URL = "https://app.rakuten.co.jp/services/api/BooksBook/Search/20170404"

    # 狙い目ジャンルとターゲット地域のマッピング
    # 001006: ビジネス・経済・就職 -> 港区 (Tokyo_Minato)
    # 001004: 小説・エッセイ -> 世田谷区 (Tokyo_Setagaya)
    # 001008: 人文・思想・社会 -> 千代田区 (Tokyo_Chiyoda)
    GENRE_STRATEGY = {
        "001006": "Tokyo_Minato",    # ビジネス -> 港区
        "001004": "Tokyo_Setagaya",  # 小説 -> 世田谷区
        "001008": "Tokyo_Chiyoda"    # 人文 -> 千代田区
    }

    # ジャンル名の日本語マッピング
    GENRE_NAMES = {
        "001006": "ビジネス・経済・就職",
        "001004": "小説・エッセイ",
        "001008": "人文・思想・社会",
    }

    def __init__(self, app_id: Optional[str] = None):
        """
        Args:
            app_id: 楽天アプリID（省略時は環境変数から取得）
        """
        self.app_id = app_id or os.getenv("RAKUTEN_APP_ID")

    def fetch_targets(self, genre_id: str = "001006", limit: int = 10) -> List[TargetBook]:
        """
        指定ジャンルのランキングからISBNを取得する

        Args:
            genre_id: 楽天ブックスのジャンルID
            limit: 取得する書籍数の上限

        Returns:
            List[TargetBook]: 対象書籍のリスト
        """
        if not self.app_id:
            print("Error: RAKUTEN_APP_ID is not set.")
            return []

        # Search APIで売上順(sales)に取得することでランキング代わりにする
        params = {
            "applicationId": self.app_id,
            "booksGenreId": genre_id,
            "sort": "sales",
            "hits": 30
        }

        try:
            response = requests.get(self.API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            targets = []
            suggested_region = self.GENRE_STRATEGY.get(genre_id, "Tokyo_Minato")

            # 先ほど確認したJSON構造に合わせてパース
            for obj in data.get("Items", []):
                # ネストされたItemキーにアクセス
                item = obj.get("Item", {})

                if len(targets) >= limit:
                    break

                isbn = item.get("isbn")
                title = item.get("title")

                # ISBNチェック
                if isbn and (len(isbn) == 13 or len(isbn) == 10):
                    targets.append(TargetBook(
                        isbn=isbn,
                        title=title,
                        genre_id=genre_id,
                        suggested_region=suggested_region
                    ))

            if not targets:
                print(f"  Warning: No books found for genre {genre_id}")

            return targets

        except Exception as e:
            # 失敗時は正直に空リストを返す（モックは返さない）
            print(f"Ranking fetch failed: {e}")
            return []

    def fetch_all_genres(self, limit_per_genre: int = 5) -> List[TargetBook]:
        """
        全ての対象ジャンルからランキングを取得する

        Args:
            limit_per_genre: ジャンルごとの取得数上限

        Returns:
            List[TargetBook]: 全ジャンル統合した対象書籍リスト
        """
        all_targets = []

        for genre_id in self.GENRE_STRATEGY.keys():
            genre_name = self.GENRE_NAMES.get(genre_id, genre_id)
            print(f"  Fetching {genre_name} ({genre_id})...")

            targets = self.fetch_targets(genre_id, limit_per_genre)
            all_targets.extend(targets)

            print(f"    -> {len(targets)} books found")

        return all_targets

    def get_genre_name(self, genre_id: str) -> str:
        """ジャンルIDから日本語名を取得"""
        return self.GENRE_NAMES.get(genre_id, genre_id)


# 単体テスト用
if __name__ == "__main__":
    print("Testing RankingFetcher")
    print("=" * 60)

    fetcher = RankingFetcher()

    # 単一ジャンルテスト
    print("\n[Business Genre Test]")
    targets = fetcher.fetch_targets("001006", limit=3)
    if targets:
        for t in targets:
            print(f"  - {t.isbn}: {t.title} -> {t.suggested_region}")
    else:
        print("  No books found")

    # 全ジャンルテスト
    print("\n[All Genres Test]")
    all_targets = fetcher.fetch_all_genres(limit_per_genre=2)
    print(f"\nTotal: {len(all_targets)} books")
    for t in all_targets:
        print(f"  - [{t.genre_id}] {t.isbn}: {t.title}")
