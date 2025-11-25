#!/usr/bin/env python3
"""
LibSearchBot - 書籍情報・蔵書状況確認スクリプト
OpenBD API と カーリル API を使用して書籍情報と図書館の在庫状況を表示する
"""

import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from modules.collector.openbd_api import OpenBDClient
from modules.collector.calil_api import CalilClient


# ===========================================
# テストデータ（デフォルト値）
# ===========================================
DEFAULT_ISBN = "9784798126708"  # リーダブルコード
DEFAULT_SYSTEM_ID = "Tokyo_Minato"  # 東京都港区

# モックモードを使用するかどうか（APIが利用できない環境ではTrueに設定）
USE_MOCK = False


def print_header(title: str):
    """セクションヘッダーを表示"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def print_book_info(book, is_mock: bool = False):
    """書籍情報を表示"""
    source = "モックデータ" if is_mock else "OpenBD"
    print_header(f"書籍情報 ({source})")

    if not book.is_found():
        print("  書籍情報が見つかりませんでした。")
        return

    print(f"  タイトル: {book.title or 'N/A'}")
    print(f"  著者:     {book.author or 'N/A'}")
    print(f"  出版社:   {book.publisher or 'N/A'}")
    print(f"  出版日:   {book.pubdate or 'N/A'}")
    print(f"  ISBN:     {book.isbn}")

    if book.cover_url:
        print(f"  書影URL:  {book.cover_url}")

    if book.description:
        # 長い説明は省略
        desc = book.description[:200] + "..." if len(book.description) > 200 else book.description
        print(f"\n  【内容紹介】")
        print(f"  {desc}")


def print_stock_info(result, system_id: str, is_mock: bool = False):
    """蔵書状況を表示"""
    source = "モックデータ" if is_mock else f"カーリル: {system_id}"
    print_header(f"蔵書状況 ({source})")

    if result.error:
        print(f"  エラー: {result.error}")
        if "CALIL_APPKEY" in result.error:
            print("\n  ※ カーリルAPIキーを取得して .env ファイルに設定してください。")
            print("    取得先: https://calil.jp/api/dashboard/")
        return

    if not result.libraries:
        print("  この地域には蔵書情報がありませんでした。")
        return

    # テーブルヘッダー
    print(f"\n  {'図書館名':<25} {'貸出状況':<12}")
    print("  " + "-" * 40)

    # 各図書館の状態を表示
    for lib in result.libraries:
        status_icon = get_status_icon(lib.status)
        print(f"  {lib.library_name:<25} {status_icon} {lib.status}")

    # サマリー
    available_count = sum(1 for lib in result.libraries if lib.status == "貸出可")
    print("\n  " + "-" * 40)
    print(f"  合計: {len(result.libraries)} 館中 {available_count} 館で貸出可能")

    # 予約URL
    if result.libraries and result.libraries[0].reserve_url:
        print(f"\n  予約URL: {result.libraries[0].reserve_url}")


def get_status_icon(status: str) -> str:
    """ステータスに応じたアイコンを返す"""
    icons = {
        "貸出可": "[OK]",
        "貸出中": "[--]",
        "蔵書なし": "[  ]",
        "館内のみ": "[館内]",
        "準備中": "[準備]",
        "予約中": "[予約]",
    }
    return icons.get(status, "[??]")


def main():
    """メイン処理"""
    # 設定値（変更可能）
    isbn = DEFAULT_ISBN
    system_id = DEFAULT_SYSTEM_ID
    use_mock = USE_MOCK

    print("\n" + "*" * 60)
    print(" LibSearchBot - 書籍蔵書状況チェッカー")
    print("*" * 60)
    print(f"\n  検索ISBN:     {isbn}")
    print(f"  対象地域ID:   {system_id}")

    if use_mock:
        print("  モード:       モックデータ使用")

    # OpenBD API で書籍情報を取得
    print("\n[1/2] OpenBD API から書籍情報を取得中...")
    openbd = OpenBDClient(use_mock=use_mock)
    book = openbd.get_book_info(isbn)

    # API接続に失敗した場合はモックモードにフォールバック
    openbd_mock_used = use_mock
    if not book.is_found() and not use_mock:
        print("  API接続に失敗。モックデータを使用します。")
        openbd = OpenBDClient(use_mock=True)
        book = openbd.get_book_info(isbn)
        openbd_mock_used = True

    print_book_info(book, is_mock=openbd_mock_used)

    # カーリル API で蔵書状況を取得
    print("\n[2/2] カーリル API から蔵書状況を取得中...")
    calil = CalilClient(use_mock=use_mock)
    result = calil.check_stock(isbn, system_id)

    # APIキーがない場合はモックモードにフォールバック
    calil_mock_used = use_mock
    if result.error and "CALIL_APPKEY" in result.error and not use_mock:
        print("  APIキー未設定。モックデータを使用します。")
        calil = CalilClient(use_mock=True)
        result = calil.check_stock(isbn, system_id)
        calil_mock_used = True

    print_stock_info(result, system_id, is_mock=calil_mock_used)

    # フッター
    print("\n" + "=" * 60)
    if openbd_mock_used or calil_mock_used:
        print(" 完了 (モックデータを使用しました)")
        print(" ※実際のAPIを使用するには:")
        print("   - OpenBD: ローカル環境で実行してください")
        print("   - カーリル: .envにCALIL_APPKEYを設定してください")
    else:
        print(" 完了")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
