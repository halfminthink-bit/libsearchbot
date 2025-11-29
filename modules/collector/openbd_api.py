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
        "9784065366431": BookInfo(
            isbn="9784065366431",
            title="変な家2 ～11の間取り図～",
            author="雨穴",
            publisher="講談社",
            pubdate="2024-03",
            description="累計200万部突破の大ベストセラー『変な家』待望の続編。不動産ミステリーの新境地。",
            cover_url="https://cover.openbd.jp/9784065366431.jpg"
        ),
        "9784822289607": BookInfo(
            isbn="9784822289607",
            title="ザ・ゴール コミック版",
            author="エリヤフ・ゴールドラット",
            publisher="ダイヤモンド社",
            pubdate="2014-12",
            description="全世界で1000万人が読んだ！製造業の常識を覆したベストセラーをコミック化。",
            cover_url="https://cover.openbd.jp/9784822289607.jpg"
        ),
        "9784478025819": BookInfo(
            isbn="9784478025819",
            title="嫌われる勇気",
            author="岸見一郎, 古賀史健",
            publisher="ダイヤモンド社",
            pubdate="2013-12",
            description="「あの人」の期待を満たすために生きてはいけない。アドラー心理学の決定版。",
            cover_url="https://cover.openbd.jp/9784478025819.jpg"
        ),
        "9784167915643": BookInfo(
            isbn="9784167915643",
            title="コンビニ人間",
            author="村田沙耶香",
            publisher="文藝春秋",
            pubdate="2018-09",
            description="芥川賞受賞作。コンビニ店員として完璧に働く女性の物語。",
            cover_url="https://cover.openbd.jp/9784167915643.jpg"
        ),
        "9784101010168": BookInfo(
            isbn="9784101010168",
            title="人間失格",
            author="太宰治",
            publisher="新潮社",
            pubdate="2006-01",
            description="太宰治の代表作。「恥の多い生涯を送ってきました」で始まる自伝的小説。",
            cover_url="https://cover.openbd.jp/9784101010168.jpg"
        ),
        "9784004140818": BookInfo(
            isbn="9784004140818",
            title="君たちはどう生きるか",
            author="吉野源三郎",
            publisher="岩波書店",
            pubdate="1982-11",
            description="人間としてどう生きるべきかを問う不朽の名作。",
            cover_url="https://cover.openbd.jp/9784004140818.jpg"
        ),
        "9784166612130": BookInfo(
            isbn="9784166612130",
            title="サピエンス全史 上",
            author="ユヴァル・ノア・ハラリ",
            publisher="河出書房新社",
            pubdate="2016-09",
            description="ホモ・サピエンスの歴史を壮大なスケールで描く世界的ベストセラー。",
            cover_url="https://cover.openbd.jp/9784166612130.jpg"
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
