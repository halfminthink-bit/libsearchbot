"""
楽天ブックスランキングフェッチャー
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
    """楽天ブックスAPIからランキングを取得する"""

    API_URL = "https://app.rakuten.co.jp/services/api/BooksBook/Ranking/20170404"

    # 狙い目ジャンルとターゲット地域のマッピング
    # 001006: ビジネス・経済・就職 -> 港区 (Tokyo_Minato)
    # 001004: 小説・エッセイ -> 世田谷区 (Tokyo_Setagaya)
    # 001008: 人文・思想・社会 -> 千代田区 (Tokyo_Chiyoda)
    GENRE_STRATEGY = {
        "001006": "Tokyo_Minato",
        "001004": "Tokyo_Setagaya",
        "001008": "Tokyo_Chiyoda",
    }

    # ジャンル名の日本語マッピング
    GENRE_NAMES = {
        "001006": "ビジネス・経済・就職",
        "001004": "小説・エッセイ",
        "001008": "人文・思想・社会",
    }

    # モックデータ（テスト用）
    MOCK_DATA = {
        "001006": [
            TargetBook(isbn="9784798126708", title="リーダブルコード", genre_id="001006", suggested_region="Tokyo_Minato"),
            TargetBook(isbn="9784822289607", title="ザ・ゴール コミック版", genre_id="001006", suggested_region="Tokyo_Minato"),
            TargetBook(isbn="9784478025819", title="嫌われる勇気", genre_id="001006", suggested_region="Tokyo_Minato"),
        ],
        "001004": [
            TargetBook(isbn="9784065366431", title="変な家2 ～11の間取り図～", genre_id="001004", suggested_region="Tokyo_Setagaya"),
            TargetBook(isbn="9784167915643", title="コンビニ人間", genre_id="001004", suggested_region="Tokyo_Setagaya"),
            TargetBook(isbn="9784101010168", title="人間失格", genre_id="001004", suggested_region="Tokyo_Setagaya"),
        ],
        "001008": [
            TargetBook(isbn="9784004140818", title="君たちはどう生きるか", genre_id="001008", suggested_region="Tokyo_Chiyoda"),
            TargetBook(isbn="9784166612130", title="サピエンス全史 上", genre_id="001008", suggested_region="Tokyo_Chiyoda"),
        ],
    }

    def __init__(self, app_id: Optional[str] = None, use_mock: bool = False):
        """
        Args:
            app_id: 楽天アプリID（省略時は環境変数から取得）
            use_mock: モックモードを使用するか
        """
        self.app_id = app_id or os.getenv("RAKUTEN_APP_ID")
        self.use_mock = use_mock or not self.app_id

    def fetch_targets(self, genre_id: str = "001006", limit: int = 10) -> List[TargetBook]:
        """
        指定ジャンルのランキングからISBNを取得する

        Args:
            genre_id: 楽天ブックスのジャンルID
            limit: 取得する書籍数の上限

        Returns:
            List[TargetBook]: 対象書籍のリスト
        """
        if self.use_mock:
            return self._fetch_mock(genre_id, limit)

        if not self.app_id:
            print("Warning: RAKUTEN_APP_ID is not set. Using mock data.")
            return self._fetch_mock(genre_id, limit)

        params = {
            "applicationId": self.app_id,
            "booksGenreId": genre_id,
            "hits": 30,  # 多めに取得してフィルタリングする
        }

        try:
            response = requests.get(self.API_URL, params=params, timeout=10)
            response.raise_for_status()
            data = response.json()

            targets = []
            suggested_region = self.GENRE_STRATEGY.get(genre_id, "Tokyo_Minato")

            for obj in data.get("Items", []):
                if len(targets) >= limit:
                    break

                # APIレスポンスは { "Item": { ... } } の形式でネストされている
                item = obj.get("Item", {})
                isbn = item.get("isbn")
                title = item.get("title")

                # ISBNがあり、かつ有効な形式のものを対象にする
                if isbn and (len(isbn) == 13 or len(isbn) == 10):
                    targets.append(TargetBook(
                        isbn=isbn,
                        title=title,
                        genre_id=genre_id,
                        suggested_region=suggested_region
                    ))

            return targets

        except requests.exceptions.RequestException as e:
            print(f"Ranking fetch failed (network error): {e}")
            return self._fetch_mock(genre_id, limit)
        except Exception as e:
            print(f"Ranking fetch failed: {e}")
            return self._fetch_mock(genre_id, limit)

    def _fetch_mock(self, genre_id: str, limit: int) -> List[TargetBook]:
        """モックデータを返す"""
        mock_list = self.MOCK_DATA.get(genre_id, [])
        return mock_list[:limit]

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

    fetcher = RankingFetcher(use_mock=True)

    # 単一ジャンルテスト
    print("\n[Business Genre Test]")
    targets = fetcher.fetch_targets("001006", limit=3)
    for t in targets:
        print(f"  - {t.isbn}: {t.title} -> {t.suggested_region}")

    # 全ジャンルテスト
    print("\n[All Genres Test]")
    all_targets = fetcher.fetch_all_genres(limit_per_genre=2)
    print(f"\nTotal: {len(all_targets)} books")
    for t in all_targets:
        print(f"  - [{t.genre_id}] {t.isbn}: {t.title}")
