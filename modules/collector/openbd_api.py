"""
OpenBD API クライアント
書誌情報（タイトル、著者、内容紹介、書影URL）を取得する
API: https://api.openbd.jp/v1/get
"""

import requests
from typing import Optional
from dataclasses import dataclass


@dataclass
class BookInfo:
    """書誌情報を格納するデータクラス"""
    isbn: str
    title: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    pubdate: Optional[str] = None
    description: Optional[str] = None
    cover_url: Optional[str] = None

    def is_found(self) -> bool:
        """書誌情報が見つかったかどうか"""
        return self.title is not None


class OpenBDClient:
    """OpenBD API クライアントクラス"""

    BASE_URL = "https://api.openbd.jp/v1/get"
    USER_AGENT = "LibSearchBot/1.0 (Python requests)"

    # テスト用のモックデータ
    MOCK_DATA = {
        "9784798126708": BookInfo(
            isbn="9784798126708",
            title="リーダブルコード",
            author="Dustin Boswell, Trevor Foucher",
            publisher="オライリー・ジャパン",
            pubdate="2012-06",
            description="美しいコードを見ると感動する。優れたコードは見た瞬間に何をしているかが伝わってくる。",
            cover_url="https://cover.openbd.jp/9784798126708.jpg"
        ),
        "9784873115658": BookInfo(
            isbn="9784873115658",
            title="リーダブルコード ―より良いコードを書くためのシンプルで実践的なテクニック",
            author="Dustin Boswell, Trevor Foucher",
            publisher="オライリージャパン",
            pubdate="2012-06",
            description="コードは理解しやすくなければならない。",
            cover_url="https://cover.openbd.jp/9784873115658.jpg"
        ),
    }

    def __init__(self, timeout: int = 10, use_mock: bool = False):
        """
        Args:
            timeout: リクエストタイムアウト秒数
            use_mock: モックモードを使用するかどうか
        """
        self.timeout = timeout
        self.headers = {"User-Agent": self.USER_AGENT}
        self.use_mock = use_mock

    def get_book_info(self, isbn: str) -> BookInfo:
        """
        ISBNから書誌情報を取得する

        Args:
            isbn: ISBN（10桁または13桁）

        Returns:
            BookInfo: 書誌情報データクラス
        """
        # ISBNからハイフンを除去
        isbn = isbn.replace("-", "")

        # モックモードの場合はモックデータを返す
        if self.use_mock:
            return self.MOCK_DATA.get(isbn, BookInfo(isbn=isbn))

        try:
            response = requests.get(
                self.BASE_URL,
                params={"isbn": isbn},
                headers=self.headers,
                timeout=self.timeout
            )
            response.raise_for_status()
            data = response.json()

            # レスポンスが空またはNullの場合（[null] など）
            # これは通信エラーではなく、単にデータなしを意味する
            if not data or data[0] is None:
                return BookInfo(isbn=isbn)

            book_data = data[0]
            return self._parse_book_data(isbn, book_data)

        except requests.RequestException as e:
            # タイムアウトや接続エラーの場合のみエラーとして扱う
            # （[null] の場合は上記で処理済み）
            return BookInfo(isbn=isbn)

    def _parse_book_data(self, isbn: str, data: dict) -> BookInfo:
        """
        APIレスポンスをパースしてBookInfoに変換する

        Args:
            isbn: ISBN
            data: APIレスポンスのJSONデータ

        Returns:
            BookInfo: パースした書誌情報
        """
        summary = data.get("summary", {})
        onix = data.get("onix", {})

        # 基本情報
        title = summary.get("title")
        author = summary.get("author")
        publisher = summary.get("publisher")
        pubdate = summary.get("pubdate")
        cover_url = summary.get("cover")

        # 内容紹介（ONIXデータから取得）
        description = None
        collateral_detail = onix.get("CollateralDetail", {})
        text_contents = collateral_detail.get("TextContent", [])

        for text_content in text_contents:
            # TextType "03" は内容紹介
            if text_content.get("TextType") == "03":
                description = text_content.get("Text")
                break

        # 内容紹介がない場合、他のテキストを探す
        if not description and text_contents:
            description = text_contents[0].get("Text")

        return BookInfo(
            isbn=isbn,
            title=title,
            author=author,
            publisher=publisher,
            pubdate=pubdate,
            description=description,
            cover_url=cover_url
        )


# 単体テスト用
if __name__ == "__main__":
    client = OpenBDClient()

    # テスト用ISBN（リーダブルコード）
    test_isbn = "9784873115658"

    print(f"Testing OpenBD API with ISBN: {test_isbn}")
    print("-" * 50)

    book = client.get_book_info(test_isbn)

    if book.is_found():
        print(f"Title: {book.title}")
        print(f"Author: {book.author}")
        print(f"Publisher: {book.publisher}")
        print(f"Pubdate: {book.pubdate}")
        print(f"Cover URL: {book.cover_url}")
        print(f"Description: {book.description[:100] if book.description else 'N/A'}...")
    else:
        print("Book not found")
