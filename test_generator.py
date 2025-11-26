#!/usr/bin/env python3
"""
LibSearchBot - Generator モジュール動作確認スクリプト
Collector でデータを取得し、Generator で記事を生成して保存する

2段階生成方式:
1. Phase 1: アウトライン生成
2. Phase 2: 記事本文生成
"""

import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)

from modules.collector.openbd_api import OpenBDClient
from modules.collector.calil_api import CalilClient
from modules.generator.llm_client import ClaudeClient
from modules.generator.builder import ArticleBuilder


# ===========================================
# テストデータ（デフォルト値）
# ===========================================
DEFAULT_ISBN = "9784798126708"  # リーダブルコード
DEFAULT_SYSTEM_ID = "Tokyo_Minato"  # 東京都港区
OUTPUT_PATH = "data/output/test_article.md"
OUTLINE_PATH = "data/output/test_outline.md"


def print_header(title: str):
    """セクションヘッダーを表示"""
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def print_step(step_num: int, total: int, message: str):
    """ステップ表示"""
    print(f"\n[{step_num}/{total}] {message}")


def main():
    """メイン処理"""
    # 設定値
    isbn = DEFAULT_ISBN
    system_id = DEFAULT_SYSTEM_ID
    output_path = OUTPUT_PATH
    outline_path = OUTLINE_PATH

    print("\n" + "*" * 60)
    print(" LibSearchBot - Generator テスト (2段階生成)")
    print("*" * 60)
    print(f"\n  検索ISBN:     {isbn}")
    print(f"  対象地域ID:   {system_id}")
    print(f"  出力先:       {output_path}")

    # ===== Step 1: OpenBD API で書籍情報を取得 =====
    print_step(1, 5, "OpenBD API から書籍情報を取得中...")

    openbd = OpenBDClient()
    book = openbd.get_book_info(isbn)

    # API接続に失敗した場合はモックモードにフォールバック
    openbd_mock_used = False
    if not book.is_found():
        print("  API接続に失敗。モックデータを使用します。")
        openbd = OpenBDClient(use_mock=True)
        book = openbd.get_book_info(isbn)
        openbd_mock_used = True

    if book.is_found():
        print(f"  -> 取得成功: 『{book.title}』 by {book.author}")
    else:
        print("  -> 書籍情報が見つかりませんでした")
        return

    # ===== Step 2: カーリル API で蔵書状況を取得 =====
    print_step(2, 5, "カーリル API から蔵書状況を取得中...")

    calil = CalilClient()
    stock = calil.check_stock(isbn, system_id)

    # APIキーがない場合はモックモードにフォールバック
    calil_mock_used = False
    if stock.error and "CALIL_APPKEY" in stock.error:
        print("  APIキー未設定。モックデータを使用します。")
        calil = CalilClient(use_mock=True)
        stock = calil.check_stock(isbn, system_id)
        calil_mock_used = True

    if stock.error:
        print(f"  -> エラー: {stock.error}")
        return
    else:
        available = sum(1 for lib in stock.libraries if lib.status == "貸出可")
        print(f"  -> 取得成功: {len(stock.libraries)}館中 {available}館で貸出可能")

    # ===== Step 3: LLMクライアントの準備 =====
    print_step(3, 5, "LLMクライアントを準備中...")

    claude = ClaudeClient()
    use_llm_mock = False

    if not claude.is_available():
        print("  ANTHROPIC_API_KEY未設定。モックモードで記事を生成します。")
        claude = ClaudeClient(use_mock=True)
        use_llm_mock = True
    else:
        print("  -> Claude API 利用可能")

    # ===== Step 4: 2段階で記事を生成 =====
    print_step(4, 5, "LLMで記事を生成中 (2段階生成)...")

    builder = ArticleBuilder(llm_client=claude)
    result = builder.build_article(book, stock, use_mock=use_llm_mock)

    if not result.is_success():
        print(f"  -> エラー: {result.error}")
        return

    print(f"  -> 生成成功!")
    print(f"     モック: {'Yes' if result.is_mock else 'No'}")
    print(f"     アウトライン: {len(result.outline)} chars")
    print(f"     記事本文:     {len(result.content)} chars")
    if result.input_tokens > 0:
        print(f"     トークン: 入力 {result.input_tokens} / 出力 {result.output_tokens}")

    # ===== Step 5: ファイルに保存 =====
    print_step(5, 5, "記事を保存中...")

    # 出力ディレクトリの作成
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # アウトラインを保存
    if builder.save_article(result.outline, outline_path):
        print(f"  -> アウトライン保存成功: {outline_path}")
    else:
        print(f"  -> アウトライン保存失敗")

    # 記事本文を保存
    if builder.save_article(result.content, output_path):
        print(f"  -> 記事保存成功: {output_path}")
    else:
        print(f"  -> 記事保存失敗")
        return

    # ===== 完了 =====
    print_header("生成された記事のプレビュー")
    preview_lines = result.content.split("\n")[:25]
    for line in preview_lines:
        print(f"  {line}")
    if len(result.content.split("\n")) > 25:
        print("  ...")
        print(f"  (以降省略。全文は {output_path} を参照)")

    # フッター
    print("\n" + "=" * 60)
    mock_info = []
    if openbd_mock_used:
        mock_info.append("OpenBD")
    if calil_mock_used:
        mock_info.append("カーリル")
    if use_llm_mock:
        mock_info.append("LLM")

    if mock_info:
        print(f" 完了 (モック使用: {', '.join(mock_info)})")
        print("\n ※実際のAPIを使用するには:")
        print("   - OpenBD: ローカル環境で実行してください")
        print("   - カーリル: .envにCALIL_APPKEYを設定してください")
        print("   - LLM: .envにANTHROPIC_API_KEYを設定してください")
    else:
        print(" 完了 (すべて実API使用)")

    print(f"\n 生成されたファイル:")
    print(f"   - アウトライン: {os.path.abspath(outline_path)}")
    print(f"   - 記事:         {os.path.abspath(output_path)}")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
