"""
投稿ログ管理モジュール
CSVファイルによる厳密なステータス管理と投稿済みファイルのアーカイブ移動を担当
"""

import csv
import os
import shutil
from datetime import datetime
from typing import Optional, List, Dict, Any


class PostLogManager:
    """投稿ログをCSVで管理するクラス"""

    CSV_HEADER = ["isbn", "region_id", "title", "filepath", "status", "post_url", "created_at", "posted_at"]

    def __init__(self, log_file: str = "data/posts_log.csv", posted_dir: str = "data/posted"):
        """
        Args:
            log_file: ログCSVファイルのパス
            posted_dir: 投稿済みファイルを移動するディレクトリ
        """
        self.log_file = log_file
        self.posted_dir = posted_dir
        self._ensure_log_exists()
        os.makedirs(posted_dir, exist_ok=True)

    def _ensure_log_exists(self):
        """ログファイルが存在しない場合はヘッダー付きで作成"""
        if not os.path.exists(self.log_file):
            # ディレクトリが存在しない場合は作成
            os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
            
            with open(self.log_file, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(self.CSV_HEADER)

    def _read_all_entries(self) -> List[Dict[str, str]]:
        """CSVファイルから全エントリを読み込む"""
        entries = []
        if not os.path.exists(self.log_file):
            return entries

        with open(self.log_file, "r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries.append(row)

        return entries

    def _write_all_entries(self, entries: List[Dict[str, str]]):
        """全エントリをCSVファイルに書き込む"""
        with open(self.log_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=self.CSV_HEADER)
            writer.writeheader()
            writer.writerows(entries)

    def is_exists(self, isbn: str, region_id: str) -> bool:
        """
        指定されたISBNとRegionの組み合わせが既にログに存在するか確認

        Args:
            isbn: ISBN
            region_id: 地域ID

        Returns:
            bool: 存在する場合True
        """
        entries = self._read_all_entries()
        for entry in entries:
            if entry.get("isbn") == isbn and entry.get("region_id") == region_id:
                return True
        return False

    def add_entry(
        self,
        isbn: str,
        region_id: str,
        title: str,
        filepath: str,
        status: str = "generated"
    ) -> bool:
        """
        新規エントリを追加（記事生成成功時に呼び出し）

        Args:
            isbn: ISBN
            region_id: 地域ID
            title: 記事タイトル
            filepath: ファイルパス
            status: ステータス（デフォルト: "generated"）

        Returns:
            bool: 追加成功かどうか
        """
        # 既に存在する場合は追加しない
        if self.is_exists(isbn, region_id):
            return False

        entries = self._read_all_entries()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        new_entry = {
            "isbn": isbn,
            "region_id": region_id,
            "title": title,
            "filepath": filepath,
            "status": status,
            "post_url": "",
            "created_at": now,
            "posted_at": ""
        }
        
        entries.append(new_entry)
        self._write_all_entries(entries)
        return True

    def mark_as_posted(self, isbn: str, region_id: str, post_url: str) -> bool:
        """
        投稿完了処理
        - ステータスを "posted" に更新
        - post_url と posted_at を記録
        - 対象のMarkdownファイルを data/output/ から data/posted/ に移動
        - CSV内の filepath も更新

        Args:
            isbn: ISBN
            region_id: 地域ID
            post_url: 投稿URL

        Returns:
            bool: 更新成功かどうか
        """
        entries = self._read_all_entries()
        updated = False
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for entry in entries:
            if entry.get("isbn") == isbn and entry.get("region_id") == region_id:
                old_filepath = entry.get("filepath", "")
                
                # ファイルが存在する場合は移動
                if old_filepath and os.path.exists(old_filepath):
                    filename = os.path.basename(old_filepath)
                    new_filepath = os.path.join(self.posted_dir, filename)
                    
                    try:
                        shutil.move(old_filepath, new_filepath)
                        entry["filepath"] = new_filepath
                    except Exception as e:
                        # 移動に失敗した場合はエラーを記録（ただしログは更新）
                        print(f"Warning: Failed to move file {old_filepath} to {new_filepath}: {e}")
                        # ファイルパスは更新しない（元のパスのまま）
                
                # ステータスとURLを更新
                entry["status"] = "posted"
                entry["post_url"] = post_url
                entry["posted_at"] = now
                updated = True
                break

        if updated:
            self._write_all_entries(entries)
            return True
        else:
            return False

    def mark_as_failed(self, isbn: str, region_id: str, error: Optional[str] = None) -> bool:
        """
        投稿失敗を記録

        Args:
            isbn: ISBN
            region_id: 地域ID
            error: エラーメッセージ（オプション）

        Returns:
            bool: 更新成功かどうか
        """
        entries = self._read_all_entries()
        updated = False

        for entry in entries:
            if entry.get("isbn") == isbn and entry.get("region_id") == region_id:
                entry["status"] = "failed"
                if error:
                    # エラーメッセージはpost_urlフィールドに記録（必要に応じて拡張可能）
                    entry["post_url"] = f"ERROR: {error}"
                updated = True
                break

        if updated:
            self._write_all_entries(entries)
            return True
        else:
            return False

    def get_pending_entries(self) -> List[Dict[str, str]]:
        """
        ステータスが "generated" のエントリを取得（投稿待ちの記事）

        Returns:
            List[Dict[str, str]]: 投稿待ちのエントリリスト
        """
        entries = self._read_all_entries()
        return [entry for entry in entries if entry.get("status") == "generated"]

    def get_entry(self, isbn: str, region_id: str) -> Optional[Dict[str, str]]:
        """
        指定されたISBNとRegionのエントリを取得

        Args:
            isbn: ISBN
            region_id: 地域ID

        Returns:
            Optional[Dict[str, str]]: エントリ（存在しない場合はNone）
        """
        entries = self._read_all_entries()
        for entry in entries:
            if entry.get("isbn") == isbn and entry.get("region_id") == region_id:
                return entry
        return None

