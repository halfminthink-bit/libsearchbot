#!/usr/bin/env python3
"""
LibSearchBot - メインエントリーポイント
CSVから書籍リストを読み込むか、楽天ランキングから自動取得して記事を生成する

Usage:
    python main.py                    # 自動ランキングモード
    python main.py --csv path/to.csv  # CSVモード
    python main.py --mock             # モックモードで実行
"""

import sys
import os
import time
import random
import argparse
import glob
from datetime import datetime
from typing import List, Optional

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(override=True)

from modules.strategist.csv_loader import CSVLoader, TargetBook as CSVTargetBook
from modules.strategist.ranking_fetcher import RankingFetcher, TargetBook as RankingTargetBook
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
DEFAULT_LIMIT_PER_GENRE = 5  # ジャンルごとのデフォルト取得数


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


class DuplicateChecker:
    """重複チェッククラス"""

    def __init__(self, output_dir: str = OUTPUT_DIR):
        """
        Args:
            output_dir: 出力ディレクトリのパス
        """
        self.output_dir = output_dir
        self.existing_keys = self._load_existing_keys()

    def _load_existing_keys(self) -> set:
        """既存ファイルからキー（ISBN×地域）を取得"""
        keys = set()
        pattern = os.path.join(self.output_dir, "*.md")

        for filepath in glob.glob(pattern):
            filename = os.path.basename(filepath)
            # ファイル名形式: {region_id}_{isbn}.md
            name_without_ext = filename.replace(".md", "")
            parts = name_without_ext.rsplit("_", 1)
            if len(parts) == 2:
                region_id, isbn = parts
                key = f"{isbn}_{region_id}"
                keys.add(key)

        return keys

    def is_duplicate(self, isbn: str, region_id: str) -> bool:
        """重複かどうかをチェック"""
        key = f"{isbn}_{region_id}"
        return key in self.existing_keys

    def add(self, isbn: str, region_id: str):
        """処理済みとしてキーを追加"""
        key = f"{isbn}_{region_id}"
        self.existing_keys.add(key)


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
        self.duplicate_checker = DuplicateChecker()

        # 統計情報
        self.stats = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "skipped": 0,
        }

    def process_book(self, isbn: str, region_id: str) -> tuple[bool, str]:
        """
        1冊の書籍を処理する

        Args:
            isbn: ISBN
            region_id: 地域ID

        Returns:
            tuple[bool, str]: (成功/失敗, メッセージ)
        """
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
        total_libs = len(stock.libraries)

        if total_libs > 0:
            Logger.info(f"       {total_libs}館中 {available}館で貸出可能")
        else:
            Logger.warning("       蔵書情報なし（予約殺到中/システム反映待ち）")

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

        # 重複チェッカーに追加
        self.duplicate_checker.add(isbn, region_id)

        return True, output_path

    def run_csv_mode(self, csv_path: str) -> dict:
        """
        CSVモードでメインループを実行する

        Args:
            csv_path: CSVファイルのパス

        Returns:
            dict: 実行統計
        """
        Logger.header("LibSearchBot - CSVモード")
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

        # TargetBookをタプルに変換
        target_list = [(t.isbn, t.region_id) for t in targets]

        return self._run_targets(target_list)

    def run_ranking_mode(self, limit_per_genre: int = DEFAULT_LIMIT_PER_GENRE) -> dict:
        """
        ランキングモードでメインループを実行する

        Args:
            limit_per_genre: ジャンルごとの取得数上限

        Returns:
            dict: 実行統計
        """
        Logger.header("LibSearchBot - 自動ランキングモード")
        Logger.info(f"出力先:  {OUTPUT_DIR}/")
        Logger.info(f"モード:  {'モック' if self.use_mock else '実API'}")
        Logger.info(f"ジャンルごと取得数: {limit_per_genre}")

        # 楽天ランキングから取得
        Logger.info("\n楽天ブックスランキングを取得中...")
        fetcher = RankingFetcher(use_mock=self.use_mock)
        targets = fetcher.fetch_all_genres(limit_per_genre=limit_per_genre)

        Logger.success(f"合計 {len(targets)} 冊を取得")

        # TargetBookをタプルに変換
        target_list = [(t.isbn, t.suggested_region) for t in targets]

        return self._run_targets(target_list)

    def _run_targets(self, targets: List[tuple]) -> dict:
        """
        ターゲットリストを処理する共通メソッド

        Args:
            targets: (isbn, region_id) のタプルリスト

        Returns:
            dict: 実行統計
        """
        # 重複除外
        original_count = len(targets)
        unique_targets = []
        seen = set()

        for isbn, region_id in targets:
            key = f"{isbn}_{region_id}"
            if key not in seen:
                # 既存ファイルもチェック
                if not self.duplicate_checker.is_duplicate(isbn, region_id):
                    unique_targets.append((isbn, region_id))
                    seen.add(key)
                else:
                    self.stats["skipped"] += 1

        skipped_count = original_count - len(unique_targets)
        if skipped_count > 0:
            Logger.info(f"重複/既存スキップ: {skipped_count}件")

        self.stats["total"] = len(unique_targets)
        Logger.info(f"処理対象: {len(unique_targets)}件")

        if len(unique_targets) == 0:
            Logger.warning("処理対象がありません")
            return self.stats

        # 各書籍を処理
        errors = []

        for i, (isbn, region_id) in enumerate(unique_targets, start=1):
            Logger.progress(i, len(unique_targets), f"『{isbn}』を処理中")

            try:
                success, message = self.process_book(isbn, region_id)

                if success:
                    self.stats["success"] += 1
                    Logger.success(f"保存完了: {message}")
                else:
                    self.stats["failed"] += 1
                    Logger.error(f"失敗: {message}")
                    errors.append({
                        "isbn": isbn,
                        "region": region_id,
                        "error": message
                    })

            except Exception as e:
                self.stats["failed"] += 1
                Logger.error(f"例外発生: {e}")
                errors.append({
                    "isbn": isbn,
                    "region": region_id,
                    "error": str(e)
                })

            # 最後の1件以外は待機
            if i < len(unique_targets):
                wait_time = random.uniform(WAIT_TIME_MIN, WAIT_TIME_MAX)
                Logger.info(f"  次の処理まで {wait_time:.1f}秒 待機...")
                time.sleep(wait_time)

        # 結果サマリー
        Logger.header("実行結果サマリー")
        Logger.info(f"総数:   {self.stats['total']}件")
        Logger.success(f"成功:   {self.stats['success']}件")
        if self.stats["skipped"] > 0:
            Logger.info(f"スキップ: {self.stats['skipped']}件")
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
        default=None,
        help="CSVモード: 入力CSVファイルのパスを指定（省略時は自動ランキングモード）"
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="モックモードで実行（APIを使用せず、テストデータを使用）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT_PER_GENRE,
        help=f"自動ランキングモード時のジャンルごと取得数 (default: {DEFAULT_LIMIT_PER_GENRE})"
    )
    return parser.parse_args()


def main():
    """メインエントリーポイント"""
    args = parse_args()

    # APIキーの確認
    calil_key = os.getenv("CALIL_APPKEY")
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    rakuten_key = os.getenv("RAKUTEN_APP_ID")

    if not args.mock:
        if not calil_key:
            Logger.warning("CALIL_APPKEY が設定されていません。カーリルAPIはモックを使用します。")
        if not anthropic_key:
            Logger.warning("ANTHROPIC_API_KEY が設定されていません。LLMはモックを使用します。")
        if not rakuten_key and args.csv is None:
            Logger.warning("RAKUTEN_APP_ID が設定されていません。楽天APIはモックを使用します。")

    # ボットを実行
    bot = LibSearchBot(use_mock=args.mock)

    if args.csv:
        # CSVモード
        stats = bot.run_csv_mode(args.csv)
    else:
        # 自動ランキングモード（デフォルト）
        stats = bot.run_ranking_mode(limit_per_genre=args.limit)

    # 終了コード
    if stats["failed"] > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
