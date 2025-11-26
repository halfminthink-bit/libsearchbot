#!/usr/bin/env python3
"""
楽天API単体テストスクリプト
RankingFetcher を呼び出し、結果（またはエラー詳細）をコンソールに表示する
"""

import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.strategist.ranking_fetcher import RankingFetcher


def main():
    """メイン処理"""
    print("=" * 60)
    print(" 楽天API 単体テスト")
    print("=" * 60)
    print()

    # 実際のAPIをテスト
    fetcher = RankingFetcher()

    if not fetcher.app_id:
        print("⚠️  Warning: RAKUTEN_APP_ID is not set.")
        print("   Set RAKUTEN_APP_ID in .env file to test real API.")
        print()

    # テスト用ジャンルID
    test_genre_id = "001006"  # ビジネス・経済・就職
    test_limit = 5

    genre_name = fetcher.get_genre_name(test_genre_id)
    print(f"Testing Genre: {genre_name} ({test_genre_id})")
    print(f"Limit: {test_limit}")
    print("-" * 60)
    print()

    try:
        print("Fetching ranking...")
        targets = fetcher.fetch_targets(test_genre_id, limit=test_limit)

        print()
        if targets:
            print(f"✅ Success: Found {len(targets)} books")
            print()
            print("Results:")
            for i, target in enumerate(targets, 1):
                print(f"  {i}. ISBN: {target.isbn}")
                print(f"     Title: {target.title}")
                print(f"     Region: {target.suggested_region}")
                print()
        else:
            print("⚠️  No books found (empty result)")

    except Exception as e:
        print(f"❌ Error occurred: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)
    print("Test completed")
    print("=" * 60)


if __name__ == "__main__":
    main()

