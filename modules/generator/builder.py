"""
記事ビルダー
収集したデータからLLMプロンプトを作成し、最終的なMarkdown記事を生成する
"""

import os
import sys
from typing import Optional
from dataclasses import dataclass

# 親ディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.collector.openbd_api import BookInfo
from modules.collector.calil_api import StockResult, LibraryStatus
from modules.generator.llm_client import ClaudeClient, LLMResponse


# 地域システムIDと日本語名のマッピング（一部）
REGION_NAMES = {
    "Tokyo_Minato": "東京都港区",
    "Tokyo_Shibuya": "東京都渋谷区",
    "Tokyo_Shinjuku": "東京都新宿区",
    "Tokyo_Chiyoda": "東京都千代田区",
    "Tokyo_Chuo": "東京都中央区",
    "Tokyo_Meguro": "東京都目黒区",
    "Tokyo_Setagaya": "東京都世田谷区",
    "Kanagawa_Yokohama": "神奈川県横浜市",
    "Osaka_Osaka": "大阪府大阪市",
}


@dataclass
class ArticleData:
    """記事生成に必要なデータをまとめるデータクラス"""
    book_info: BookInfo
    stock_result: StockResult
    region_name: str
    keyword: Optional[str] = None


class ArticleBuilder:
    """記事ビルダークラス"""

    # システムプロンプト（ペルソナ設定）
    SYSTEM_PROMPT = """あなたは地元の図書館事情に詳しいベテラン司書兼ブックガイドです。

読者に対して親しみやすく、かつ専門的な知識を持って情報を提供します。
以下の点を意識して記事を執筆してください：

- 読者が「この本を読みたい！」と思えるような魅力的な導入
- 図書館を利用するメリットを伝える
- 具体的で実用的な情報を提供する
- 借りられなかった場合の代替案（電子書籍、購入など）も提示する

重要: 在庫状況テーブルは最新のAPI取得結果です。改変せずにそのまま記事内のしかるべき場所に配置してください。"""

    # プロンプトテンプレート
    PROMPT_TEMPLATE = """以下の情報を元に、SEOに強い図書館蔵書案内の記事を執筆してください。

## 書籍情報
- タイトル: {title}
- 著者: {author}
- 出版社: {publisher}
- 出版日: {pubdate}
- ISBN: {isbn}
{description_section}

## 対象地域
{region_name}

## 蔵書状況テーブル（※このテーブルは最新のAPI取得結果なので、改変せずにそのまま記事内のしかるべき場所に配置してください）

{stock_table}

## 記事の構成要件
1. **タイトル**: 【{region_name}】『{title}』の在庫がある図書館・貸出状況まとめ
2. **導入部**: この本の魅力と「無料で読むなら図書館」という訴求（2-3段落）
3. **蔵書状況セクション**: 上記のテーブルをそのまま掲載し、簡単な解説を付ける
4. **図書館ガイドセクション**: 対象地域の図書館の一般的な特徴やアクセス情報
5. **借りられなかった場合セクション**: 予約方法、電子書籍、Amazon購入への誘導
6. **まとめ**: 図書館利用のメリットを改めて伝える

Markdown形式で出力してください。"""

    def __init__(self, llm_client: Optional[ClaudeClient] = None):
        """
        Args:
            llm_client: LLMクライアント（省略時は新規作成）
        """
        self.llm_client = llm_client or ClaudeClient()

    def format_stock_table(self, stock_result: StockResult) -> str:
        """
        蔵書検索結果をMarkdownテーブル形式に変換する

        Args:
            stock_result: カーリルAPIの検索結果

        Returns:
            str: Markdownテーブル形式のテキスト
        """
        if not stock_result.libraries:
            return "| 図書館名 | 貸出状況 | 予約 |\n|---|---|---|\n| *蔵書情報がありませんでした* | - | - |"

        lines = ["| 図書館名 | 貸出状況 | 予約 |", "|---|---|---|"]

        for lib in stock_result.libraries:
            status_emoji = self._get_status_emoji(lib.status)
            reserve_link = self._format_reserve_link(lib.reserve_url) if lib.status != "蔵書なし" else "-"
            lines.append(f"| {lib.library_name} | {status_emoji} {lib.status} | {reserve_link} |")

        # サマリー行を追加
        available_count = sum(1 for lib in stock_result.libraries if lib.status == "貸出可")
        total_count = len(stock_result.libraries)
        lines.append("")
        lines.append(f"**{total_count}館中 {available_count}館で貸出可能** （調査時点）")

        return "\n".join(lines)

    def _get_status_emoji(self, status: str) -> str:
        """ステータスに応じた絵文字を返す"""
        emoji_map = {
            "貸出可": "🟢",
            "貸出中": "🔴",
            "蔵書なし": "⚪",
            "館内のみ": "🟡",
            "準備中": "🟠",
            "予約中": "🔵",
        }
        return emoji_map.get(status, "⚪")

    def _format_reserve_link(self, url: Optional[str]) -> str:
        """予約URLをMarkdownリンク形式に変換"""
        if not url:
            return "-"
        return f"[予約する]({url})"

    def get_region_name(self, system_id: str) -> str:
        """システムIDから日本語の地域名を取得"""
        return REGION_NAMES.get(system_id, system_id)

    def create_prompt(
        self,
        book_info: BookInfo,
        stock_result: StockResult,
        region_name: Optional[str] = None
    ) -> str:
        """
        LLMへのプロンプトを作成する

        Args:
            book_info: 書籍情報
            stock_result: 蔵書検索結果
            region_name: 地域名（省略時はシステムIDから推測）

        Returns:
            str: プロンプトテキスト
        """
        # 地域名の取得
        if not region_name:
            region_name = self.get_region_name(stock_result.system_id)

        # 蔵書テーブルの作成
        stock_table = self.format_stock_table(stock_result)

        # 内容紹介セクション
        description_section = ""
        if book_info.description:
            description_section = f"- 内容紹介: {book_info.description[:300]}..."

        # プロンプトの組み立て
        prompt = self.PROMPT_TEMPLATE.format(
            title=book_info.title or "不明",
            author=book_info.author or "不明",
            publisher=book_info.publisher or "不明",
            pubdate=book_info.pubdate or "不明",
            isbn=book_info.isbn,
            description_section=description_section,
            region_name=region_name,
            stock_table=stock_table
        )

        return prompt

    def build_article(
        self,
        book_info: BookInfo,
        stock_result: StockResult,
        region_name: Optional[str] = None,
        use_mock: bool = False
    ) -> LLMResponse:
        """
        記事を生成する

        Args:
            book_info: 書籍情報
            stock_result: 蔵書検索結果
            region_name: 地域名（省略時はシステムIDから推測）
            use_mock: モックモードを使用するか

        Returns:
            LLMResponse: 生成された記事を含むレスポンス
        """
        if not region_name:
            region_name = self.get_region_name(stock_result.system_id)

        # プロンプトの作成
        prompt = self.create_prompt(book_info, stock_result, region_name)
        stock_table = self.format_stock_table(stock_result)

        # モックモード用のコンテキスト
        mock_context = {
            "title": book_info.title or "書籍タイトル",
            "author": book_info.author or "著者名",
            "region": region_name,
            "stock_table": stock_table
        }

        # モックモードの設定
        if use_mock and not self.llm_client.use_mock:
            self.llm_client.use_mock = True

        # LLMで記事を生成
        response = self.llm_client.generate(
            prompt=prompt,
            system_prompt=self.SYSTEM_PROMPT,
            mock_context=mock_context
        )

        return response

    def save_article(self, content: str, filepath: str) -> bool:
        """
        記事をファイルに保存する

        Args:
            content: 記事の内容
            filepath: 保存先のファイルパス

        Returns:
            bool: 保存成功かどうか
        """
        try:
            # ディレクトリがなければ作成
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return True
        except Exception as e:
            print(f"Error saving article: {e}")
            return False


# 単体テスト用
if __name__ == "__main__":
    from modules.collector.openbd_api import BookInfo
    from modules.collector.calil_api import StockResult, LibraryStatus

    # テストデータ
    book = BookInfo(
        isbn="9784798126708",
        title="リーダブルコード",
        author="Dustin Boswell, Trevor Foucher",
        publisher="オライリー・ジャパン",
        pubdate="2012-06",
        description="美しいコードを見ると感動する。優れたコードは見た瞬間に何をしているかが伝わってくる。"
    )

    stock = StockResult(
        isbn="9784798126708",
        system_id="Tokyo_Minato",
        libraries=[
            LibraryStatus("港区立みなと図書館", "貸出可", "https://calil.jp/reserve"),
            LibraryStatus("港区立三田図書館", "貸出中", "https://calil.jp/reserve"),
            LibraryStatus("港区立麻布図書館", "貸出可", "https://calil.jp/reserve"),
        ]
    )

    print("Testing ArticleBuilder")
    print("=" * 60)

    builder = ArticleBuilder()

    # テーブルフォーマットのテスト
    print("\n[Stock Table]")
    print(builder.format_stock_table(stock))

    # プロンプト作成のテスト
    print("\n[Generated Prompt]")
    prompt = builder.create_prompt(book, stock)
    print(prompt[:1000] + "...")
