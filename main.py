#!/usr/bin/env python3
"""
LibSearchBot - メインエントリーポイント
CSVから書籍リストを読み込み、連続して記事を生成する

Usage:
    python main.py
    python main.py --csv path/to/custom.csv
    python main.py --mock  # モックモードで実行
"""

import sys
import os
import time
import random
import argparse
from datetime import datetime

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)

from modules.strategist.csv_loader import CSVLoader, TargetBook
from modules.collector.openbd_api import OpenBDClient
from modules.collector.calil_api import CalilClient
from modules.generator.llm_client import ClaudeClient
from modules.generator.builder import ArticleBuilder, REGION_NAMES


# ===========================================
# 設定
# ===========================================
DEFAULT_CSV_PATH = "data/input/target_books.csv"
OUTPUT_DIR = "data/output"
WAIT_TIME_MIN = 5  # 最小待機時間（秒）
WAIT_TIME_MAX = 10  # 最大待機時間（秒）


class Logger:
    """シンプルなロガークラス"""

    COLORS = {
        "reset": "\033[0m",
        "bold": "\033[1m",
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "magenta": "\033[95m",
        "cyan": "\033[96m",
    }

    @staticmethod
    def _color(text: str, color: str) -> str:
        """テキストに色を付ける"""
        return f"{Logger.COLORS.get(color, '')}{text}{Logger.COLORS['reset']}"

    @staticmethod
    def header(text: str):
        """ヘッダー出力"""
        print("\n" + "=" * 70)
        print(Logger._color(f" {text}", "bold"))
        print("=" * 70)

    @staticmethod
    def info(text: str):
        """情報出力"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {text}")

    @staticmethod
    def success(text: str):
        """成功出力"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {Logger._color('✓', 'green')} {text}")

    @staticmethod
    def warning(text: str):
        """警告出力"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {Logger._color('⚠', 'yellow')} {text}")

    @staticmethod
    def error(text: str):
        """エラー出力"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {Logger._color('✗', 'red')} {text}")

    @staticmethod
    def progress(current: int, total: int, text: str):
        """進捗出力"""
        bar_length = 30
        filled = int(bar_length * current / total)
        bar = "█" * filled + "░" * (bar_length - filled)
        percent = current / total * 100
        print(f"\n[{bar}] {percent:.0f}% ({current}/{total}) - {text}")


class LibSearchBot:
    """LibSearchBot メインクラス"""

    def __init__(self, use_mock: bool = False):
        """
        Args:
            use_mock: モックモードを使用するか
        """
        self.use_mock = use_mock
        self.openbd = OpenBDClient(use_mock=use_mock)
        self.calil = CalilClient(use_mock=use_mock)
        self.claude = ClaudeClient(use_mock=use_mock)
        self.builder = ArticleBuilder(llm_client=self.claude)

        # 統計情報
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
        }

    def process_book(self, target: TargetBook) -> tuple[bool, str]:
        """
        1冊の書籍を処理する

        Args:
            target: ターゲット書籍情報

        Returns:
            tuple[bool, str]: (成功/失敗, メッセージ)
        """
        isbn = target.isbn
        region_id = target.region_id
        region_name = REGION_NAMES.get(region_id, region_id)

        Logger.info(f"ISBN: {isbn} / Region: {region_name}")

        # Step 1: OpenBD API で書籍情報を取得
        Logger.info("  [1/3] 書籍情報を取得中...")
        book = self.openbd.get_book_info(isbn)

        if not book.is_found():
            # モックモードでなければフォールバック
            if not self.use_mock:
                Logger.warning("  OpenBD接続失敗。モックデータを使用します。")
                self.openbd = OpenBDClient(use_mock=True)
                book = self.openbd.get_book_info(isbn)
                self.openbd = OpenBDClient(use_mock=self.use_mock)  # 元に戻す

            if not book.is_found():
                return False, "書籍情報が取得できませんでした"

        Logger.info(f"       『{book.title}』 by {book.author}")

        # Step 2: カーリル API で蔵書状況を取得
        Logger.info("  [2/3] 蔵書状況を取得中...")
        stock = self.calil.check_stock(isbn, region_id)

        if stock.error:
            if "CALIL_APPKEY" in stock.error and not self.use_mock:
                Logger.warning("  APIキー未設定。モックデータを使用します。")
                calil_mock = CalilClient(use_mock=True)
                stock = calil_mock.check_stock(isbn, region_id)
            else:
                return False, f"蔵書情報取得エラー: {stock.error}"

        available = sum(1 for lib in stock.libraries if lib.status == "貸出可")
        Logger.info(f"       {len(stock.libraries)}館中 {available}館で貸出可能")

        # Step 3: 記事を生成
        Logger.info("  [3/3] 記事を生成中 (2段階生成)...")
        result = self.builder.build_article(book, stock, region_name)

        if not result.is_success():
            return False, f"記事生成エラー: {result.error}"

        Logger.info(f"       アウトライン: {len(result.outline)} chars / 記事: {len(result.content)} chars")

        # Step 4: ファイルに保存
        output_filename = f"{region_id}_{isbn}.md"
        output_path = os.path.join(OUTPUT_DIR, output_filename)

        os.makedirs(OUTPUT_DIR, exist_ok=True)

        if not self.builder.save_article(result.content, output_path):
            return False, "ファイル保存に失敗しました"

        return True, output_path

    def run(self, csv_path: str) -> dict:
        """
        メインループを実行する

        Args:
            csv_path: CSVファイルのパス

        Returns:
            dict: 実行統計
        """
        Logger.header("LibSearchBot - バッチ記事生成")
        Logger.info(f"入力CSV: {csv_path}")
        Logger.info(f"出力先:  {OUTPUT_DIR}/")
        Logger.info(f"モード:  {'モック' if self.use_mock else '実API'}")

        # CSVを読み込む
        Logger.info("CSVファイルを読み込み中...")
        try:
            loader = CSVLoader(csv_path)
            targets = loader.load()
        except FileNotFoundError as e:
            Logger.error(f"ファイルが見つかりません: {e}")
            return self.stats
        except ValueError as e:
            Logger.error(f"CSVフォーマットエラー: {e}")
            return self.stats

        self.stats["total"] = len(targets)
        Logger.success(f"{len(targets)}件のターゲットを読み込みました")

        if len(targets) == 0:
            Logger.warning("処理対象がありません")
            return self.stats

        # 各書籍を処理
        errors = []

        for i, target in enumerate(targets, start=1):
            Logger.progress(i, len(targets), f"『{target.isbn}』を処理中")

            try:
                success, message = self.process_book(target)

                if success:
                    self.stats["success"] += 1
                    Logger.success(f"保存完了: {message}")
                else:
                    self.stats["failed"] += 1
                    Logger.error(f"失敗: {message}")
                    errors.append({
                        "isbn": target.isbn,
                        "region": target.region_id,
                        "error": message
                    })

            except Exception as e:
                self.stats["failed"] += 1
                Logger.error(f"例外発生: {e}")
                errors.append({
                    "isbn": target.isbn,
                    "region": target.region_id,
                    "error": str(e)
                })

            # 最後の1件以外は待機
            if i < len(targets):
                wait_time = random.uniform(WAIT_TIME_MIN, WAIT_TIME_MAX)
                Logger.info(f"  次の処理まで {wait_time:.1f}秒 待機...")
                time.sleep(wait_time)

        # 結果サマリー
        Logger.header("実行結果サマリー")
        Logger.info(f"総数:   {self.stats['total']}件")
        Logger.success(f"成功:   {self.stats['success']}件")
        if self.stats["failed"] > 0:
            Logger.error(f"失敗:   {self.stats['failed']}件")

            if errors:
                print("\n失敗した項目:")
                for err in errors:
                    print(f"  - ISBN: {err['isbn']}, Region: {err['region']}")
                    print(f"    Error: {err['error']}")

        Logger.info(f"\n生成されたファイルは {os.path.abspath(OUTPUT_DIR)}/ にあります")

        return self.stats


def parse_args():
    """コマンドライン引数をパース"""
    parser = argparse.ArgumentParser(
        description="LibSearchBot - 図書館蔵書情報からSEO記事を自動生成"
    )
    parser.add_argument(
        "--csv",
        default=DEFAULT_CSV_PATH,
        help=f"入力CSVファイルのパス (default: {DEFAULT_CSV_PATH})"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="モックモードで実行（APIを使用せず、テストデータを使用）"
    )
    return parser.parse_args()


def main():
    """メインエントリーポイント"""
    args = parse_args()

    # APIキーの確認
    calil_key = os.getenv("CALIL_APPKEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")

    if not args.mock:
        if not calil_key:
            Logger.warning("CALIL_APPKEY が設定されていません。カーリルAPIはモックを使用します。")
        if not anthropic_key:
            Logger.warning("ANTHROPIC_API_KEY が設定されていません。LLMはモックを使用します。")

    # ボットを実行
    bot = LibSearchBot(use_mock=args.mock)
    stats = bot.run(args.csv)

    # 終了コード
    if stats["failed"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
