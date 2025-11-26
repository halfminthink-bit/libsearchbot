"""
カーリル API クライアント
蔵書状況を取得する（ポーリング処理対応）
API: http://api.calil.jp/check
"""

import os
import time
import requests
from typing import Optional
from dataclasses import dataclass, field
from dotenv import load_dotenv


@dataclass
class LibraryStatus:
    """図書館ごとの蔵書状況"""
    library_name: str
    status: str  # 貸出可, 貸出中, 蔵書なし, 館内のみ, 準備中 など
    reserve_url: Optional[str] = None


@dataclass
class StockResult:
    """蔵書検索結果"""
    isbn: str
    system_id: str
    libraries: list[LibraryStatus] = field(default_factory=list)
    error: Optional[str] = None

    def has_available(self) -> bool:
        """貸出可能な図書館があるかどうか"""
        return any(lib.status == "貸出可" for lib in self.libraries)


class CalilClient:
    """カーリル API クライアントクラス"""

    CHECK_URL = "https://api.calil.jp/check"
    USER_AGENT = "LibSearchBot/1.0 (Python requests)"

    # ステータスコードの日本語マッピング
    STATUS_MAP = {
        "貸出可": "貸出可",
        "蔵書あり": "貸出可",
        "貸出中": "貸出中",
        "蔵書なし": "蔵書なし",
        "館内のみ": "館内のみ",
        "準備中": "準備中",
        "予約中": "予約中",
        "休館中": "休館中",
    }

    def __init__(self, appkey: Optional[str] = None, timeout: int = 10, use_mock: bool = False):
        """
        Args:
            appkey: カーリルAPIキー（省略時は環境変数から取得）
            timeout: リクエストタイムアウト秒数
            use_mock: モックモードを使用するかどうか
        """
        load_dotenv(override=True)

        self.appkey = appkey or os.getenv("CALIL_APPKEY")
        self.timeout = timeout
        self.max_polls = 5  # 最大ポーリング回数
        self.poll_interval = 2  # ポーリング間隔（秒）
        self.headers = {"User-Agent": self.USER_AGENT}
        self.use_mock = use_mock

    def _get_mock_result(self, isbn: str, system_id: str) -> StockResult:
        """テスト用のモックデータを返す"""
        mock_libraries = [
            LibraryStatus("港区立みなと図書館", "貸出可", "https://calil.jp/reserve"),
            LibraryStatus("港区立三田図書館", "貸出中", "https://calil.jp/reserve"),
            LibraryStatus("港区立麻布図書館", "貸出可", "https://calil.jp/reserve"),
            LibraryStatus("港区立赤坂図書館", "貸出中", "https://calil.jp/reserve"),
            LibraryStatus("港区立高輪図書館", "蔵書なし", None),
        ]
        return StockResult(isbn=isbn, system_id=system_id, libraries=mock_libraries)

    def check_stock(self, isbn: str, system_id: str) -> StockResult:
        """
        指定した地域の蔵書状況を取得する

        Args:
            isbn: ISBN（10桁または13桁）
            system_id: カーリルのシステムID（例: Tokyo_Minato）

        Returns:
            StockResult: 蔵書検索結果
        """
        # ISBNからハイフンを除去
        isbn = isbn.replace("-", "")

        # モックモードの場合はモックデータを返す
        if self.use_mock:
            return self._get_mock_result(isbn, system_id)

        if not self.appkey:
            return StockResult(
                isbn=isbn,
                system_id=system_id,
                error="CALIL_APPKEY is not set. Please set it in .env file."
            )

        params = {
            "appkey": self.appkey,
            "isbn": isbn,
            "systemid": system_id,
            "format": "json",
            "callback": "no"  # JSON形式を取得（JSONPを無効化）
        }

        session = None  # セッションキー（ポーリング用）

        for attempt in range(self.max_polls):
            try:
                # セッションキーがある場合は追加
                if session:
                    params["session"] = session

                response = requests.get(
                    self.CHECK_URL,
                    params=params,
                    headers=self.headers,
                    timeout=self.timeout
                )
                response.raise_for_status()

                # 純粋なJSONとしてパース
                data = response.json()

                # ポーリング継続判定
                continue_flag = data.get("continue", 0)
                session = data.get("session")

                if continue_flag == 1:
                    print(f"  Polling... (attempt {attempt + 1}/{self.max_polls})")
                    time.sleep(self.poll_interval)
                    continue

                # データ取得完了
                return self._parse_result(isbn, system_id, data)

            except requests.RequestException as e:
                return StockResult(
                    isbn=isbn,
                    system_id=system_id,
                    error=f"API request error: {e}"
                )
            except json.JSONDecodeError as e:
                return StockResult(
                    isbn=isbn,
                    system_id=system_id,
                    error=f"JSON parse error: {e}"
                )

        # 最大ポーリング回数に達した
        return StockResult(
            isbn=isbn,
            system_id=system_id,
            error="Max polling attempts reached. Please try again later."
        )

    def _parse_result(self, isbn: str, system_id: str, data: dict) -> StockResult:
        """
        APIレスポンスをパースしてStockResultに変換する

        Args:
            isbn: ISBN
            system_id: システムID
            data: APIレスポンスのJSONデータ

        Returns:
            StockResult: パースした蔵書検索結果
        """
        libraries = []

        # booksデータからシステムIDごとの結果を取得
        books = data.get("books", {})
        isbn_data = books.get(isbn, {})
        system_data = isbn_data.get(system_id, {})

        if not system_data:
            return StockResult(
                isbn=isbn,
                system_id=system_id,
                libraries=[],
                error=None  # 蔵書なしの場合もエラーではない
            )

        # 各図書館の状態をパース
        libkeys = system_data.get("libkey", {})
        reserve_url = system_data.get("reserveurl")

        for library_name, status in libkeys.items():
            # ステータスを日本語に変換
            status_ja = self.STATUS_MAP.get(status, status)

            libraries.append(LibraryStatus(
                library_name=library_name,
                status=status_ja,
                reserve_url=reserve_url
            ))

        return StockResult(
            isbn=isbn,
            system_id=system_id,
            libraries=libraries
        )


# 単体テスト用
if __name__ == "__main__":
    client = CalilClient()

    # テスト用データ
    test_isbn = "9784798126708"  # リーダブルコード
    test_system_id = "Tokyo_Minato"  # 東京都港区

    print(f"Testing Calil API")
    print(f"ISBN: {test_isbn}")
    print(f"System ID: {test_system_id}")
    print("-" * 50)

    result = client.check_stock(test_isbn, test_system_id)

    if result.error:
        print(f"Error: {result.error}")
    elif result.libraries:
        print(f"Found {len(result.libraries)} libraries:")
        for lib in result.libraries:
            print(f"  - {lib.library_name}: {lib.status}")
        print(f"\nAvailable for borrowing: {'Yes' if result.has_available() else 'No'}")
    else:
        print("No stock information found")
