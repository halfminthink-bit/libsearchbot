"""
記事ビルダー
収集したデータからLLMプロンプトを作成し、最終的なMarkdown記事を生成する

2段階生成方式:
1. create_outline(): アウトライン生成
2. create_draft(): 記事本文生成
"""

import os
import sys
from typing import Optional
from dataclasses import dataclass

from dotenv import load_dotenv
load_dotenv(override=True)

from jinja2 import Environment, FileSystemLoader, select_autoescape

# 親ディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from modules.collector.openbd_api import BookInfo
from modules.collector.calil_api import StockResult, LibraryStatus
from modules.generator.llm_client import ClaudeClient, LLMResponse


# プレースホルダー定数（テンプレートとコードで共有）
STOCK_TABLE_PLACEHOLDER = "[[STOCK_TABLE_HERE]]"


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


@dataclass
class BuildResult:
    """記事ビルド結果を格納するデータクラス"""
    content: str
    outline: str
    is_mock: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    error: Optional[str] = None

    def is_success(self) -> bool:
        """ビルドが成功かどうか"""
        return self.error is None and len(self.content) > 0


class ArticleBuilder:
    """記事ビルダークラス（2段階生成対応）"""

    # モックアウトライン用テンプレート
    MOCK_OUTLINE_TEMPLATE = """## 【{region_name}】『{book_title}』の在庫がある図書館・貸出状況まとめ

### H2: はじめに - 『{book_title}』を無料で読む方法
- 本の魅力を簡潔に紹介
- 図書館なら無料で借りられることを訴求

### H2: {region_name}の図書館での蔵書・貸出状況
- {stock_table_placeholder}
- 貸出状況の見方を解説

### H2: {region_name}の図書館ガイド
- 主要図書館へのアクセス
- 図書館カードの作り方
- 便利なサービス（予約、取り寄せなど）

### H2: 借りられなかった場合の代替案
- 予約サービスを利用する
- 電子書籍で読む（Kindle Unlimitedなど）
- 購入する（Amazonリンク）

### H2: まとめ
- 図書館利用のメリット再確認
- 行動を促すCTA
"""

    # モック記事用テンプレート
    MOCK_ARTICLE_TEMPLATE = """# 【{region_name}】『{book_title}』の在庫がある図書館・貸出状況まとめ

## はじめに - 『{book_title}』を無料で読む方法

こんにちは！地元の図書館事情に詳しいベテラン司書です。

今回は **『{book_title}』** （{author}著）を{region_name}エリアの図書館で借りる方法をご紹介しますね。

この本、とても人気がありますよね。でも、わざわざ購入しなくても、お近くの図書館で無料で借りられるかもしれません！

## {region_name}の図書館での蔵書・貸出状況

さっそく、{region_name}の図書館での在庫状況を見ていきましょう。

{stock_table}

上の表で「貸出可」となっている図書館では、今すぐ借りることができますよ。

## {region_name}の図書館ガイド

{region_name}には複数の図書館があり、それぞれ特色があります。

図書館カードをお持ちでない方は、お住まいの地域の図書館で簡単に作れます。身分証明書をお忘れなく！

また、ほとんどの図書館ではインターネットからの予約サービスも利用できます。貸出中の本も予約しておけば、返却され次第連絡がもらえますよ。

## 借りられなかった場合の代替案

人気の本は貸出中のことも多いですよね。そんなときの選択肢をご紹介します。

### 予約サービスを利用する

貸出中でも予約しておけば、順番が来たら借りられます。

### 電子書籍で読む

Kindle Unlimitedなら、対象の本が読み放題です。

### 購入する

どうしても今すぐ読みたい方は、[Amazonで見る](https://www.amazon.co.jp/dp/{isbn}?tag={affiliate_tag}) から購入もできます。

<a href="{kindle_url}" target="_blank" rel="noopener">📚 Kindle Unlimitedで読む</a>

<a href="{audible_url}" target="_blank" rel="noopener">🎧 Audibleで聴く</a>

## まとめ

『{book_title}』は{region_name}の図書館で無料で読むことができます。

ぜひお近くの図書館を訪れてみてくださいね！
"""

    def __init__(self, llm_client: Optional[ClaudeClient] = None):
        """
        Args:
            llm_client: LLMクライアント（省略時は新規作成）
        """
        self.llm_client = llm_client or ClaudeClient()

        # Jinja2環境の初期化
        template_dir = os.path.join(os.path.dirname(__file__), "templates")
        self.jinja_env = Environment(
            loader=FileSystemLoader(template_dir),
            autoescape=select_autoescape(['html', 'xml'])
        )

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

    def _calculate_scarcity(self, stock_result: StockResult) -> bool:
        """
        在庫逼迫度を計算する
        貸出可の図書館が全体の30%未満の場合にTrueを返す

        Args:
            stock_result: 蔵書検索結果

        Returns:
            bool: 在庫が逼迫しているかどうか
        """
        if not stock_result.libraries:
            return True  # 蔵書がない場合は逼迫とみなす

        total = len(stock_result.libraries)
        available = sum(1 for lib in stock_result.libraries if lib.status == "貸出可")

        # 30%未満なら逼迫
        return (available / total) < 0.3

    def create_outline(
        self,
        book_info: BookInfo,
        region_name: str
    ) -> LLMResponse:
        """
        アウトラインを生成する（Phase 1）

        Args:
            book_info: 書籍情報
            region_name: 地域名

        Returns:
            LLMResponse: 生成されたアウトライン
        """
        # Jinja2テンプレートを読み込み
        template = self.jinja_env.get_template("outline_prompt.j2")

        # プロンプトをレンダリング
        prompt = template.render(
            book_title=book_info.title or "不明",
            author=book_info.author or "不明",
            publisher=book_info.publisher or "不明",
            description=book_info.description[:300] if book_info.description else "情報なし",
            region_name=region_name,
            stock_table_placeholder=STOCK_TABLE_PLACEHOLDER
        )

        # モックモードの場合
        if self.llm_client.use_mock:
            mock_outline = self.MOCK_OUTLINE_TEMPLATE.format(
                book_title=book_info.title or "書籍タイトル",
                region_name=region_name,
                stock_table_placeholder=STOCK_TABLE_PLACEHOLDER
            )
            return LLMResponse(
                content=mock_outline,
                model="mock",
                is_mock=True
            )

        # LLMでアウトライン生成
        return self.llm_client.generate(
            prompt=prompt,
            system_prompt="あなたはSEOに強いウェブメディアの編集者です。",
            temperature=0.5
        )

    def create_draft(
        self,
        book_info: BookInfo,
        region_name: str,
        stock_table_str: str,
        outline: str,
        stock_result: Optional[StockResult] = None
    ) -> LLMResponse:
        """
        記事本文を生成する（Phase 2）

        Args:
            book_info: 書籍情報
            region_name: 地域名
            stock_table_str: 在庫テーブル文字列
            outline: アウトライン
            stock_result: 蔵書検索結果（在庫逼迫度計算用）

        Returns:
            LLMResponse: 生成された記事本文
        """
        # Jinja2テンプレートを読み込み
        template = self.jinja_env.get_template("draft_prompt.j2")

        # 在庫逼迫度を計算
        is_stock_scarce = self._calculate_scarcity(stock_result) if stock_result else False

        # アフィリエイト関連の環境変数を取得
        affiliate_tag = os.getenv("AMAZON_AFFILIATE_TAG", "mytag-22")
        kindle_url = os.getenv("KINDLE_PROMO_URL", f"https://www.amazon.co.jp/kindle-dbs/hz/signup?tag={affiliate_tag}")
        audible_url = os.getenv("AUDIBLE_PROMO_URL", f"https://www.amazon.co.jp/hz/audible/mlp?tag={affiliate_tag}")

        # プロンプトをレンダリング
        prompt = template.render(
            book_title=book_info.title or "不明",
            author=book_info.author or "不明",
            description=book_info.description[:300] if book_info.description else "情報なし",
            region_name=region_name,
            outline=outline,
            stock_table_placeholder=STOCK_TABLE_PLACEHOLDER,
            stock_table_string=stock_table_str,
            isbn=book_info.isbn,
            is_stock_scarce=is_stock_scarce,
            affiliate_tag=affiliate_tag,
            kindle_url=kindle_url,
            audible_url=audible_url
        )

        # モックモードの場合
        if self.llm_client.use_mock:
            mock_article = self.MOCK_ARTICLE_TEMPLATE.format(
                book_title=book_info.title or "書籍タイトル",
                author=book_info.author or "著者名",
                region_name=region_name,
                stock_table=stock_table_str,
                isbn=book_info.isbn,
                affiliate_tag=affiliate_tag,
                kindle_url=kindle_url,
                audible_url=audible_url
            )
            return LLMResponse(
                content=mock_article,
                model="mock",
                is_mock=True
            )

        # LLMで記事生成
        return self.llm_client.generate(
            prompt=prompt,
            system_prompt="あなたは地元の図書館事情に詳しいベテラン司書兼ブックガイドです。",
            temperature=0.7,
            max_tokens=8192
        )

    def build_article(
        self,
        book_info: BookInfo,
        stock_result: StockResult,
        region_name: Optional[str] = None,
        use_mock: bool = False
    ) -> BuildResult:
        """
        記事を生成する（2段階生成のオーケストレーター）

        Args:
            book_info: 書籍情報
            stock_result: 蔵書検索結果
            region_name: 地域名（省略時はシステムIDから推測）
            use_mock: モックモードを使用するか

        Returns:
            BuildResult: 生成された記事を含む結果
        """
        if not region_name:
            region_name = self.get_region_name(stock_result.system_id)

        # モックモードの設定
        if use_mock and not self.llm_client.use_mock:
            self.llm_client.use_mock = True

        total_input_tokens = 0
        total_output_tokens = 0

        # Phase 1: アウトライン生成
        print("    Phase 1: アウトライン生成中...")
        outline_response = self.create_outline(book_info, region_name)

        if not outline_response.is_success():
            return BuildResult(
                content="",
                outline="",
                error=f"Outline generation failed: {outline_response.error}"
            )

        total_input_tokens += outline_response.input_tokens
        total_output_tokens += outline_response.output_tokens

        # 在庫テーブルを生成
        stock_table_str = self.format_stock_table(stock_result)

        # Phase 2: 記事本文生成
        print("    Phase 2: 記事本文生成中...")
        draft_response = self.create_draft(
            book_info,
            region_name,
            stock_table_str,
            outline_response.content,
            stock_result
        )

        if not draft_response.is_success():
            return BuildResult(
                content="",
                outline=outline_response.content,
                error=f"Draft generation failed: {draft_response.error}"
            )

        total_input_tokens += draft_response.input_tokens
        total_output_tokens += draft_response.output_tokens

        return BuildResult(
            content=draft_response.content,
            outline=outline_response.content,
            is_mock=outline_response.is_mock or draft_response.is_mock,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens
        )

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

    print("Testing ArticleBuilder (2-phase generation)")
    print("=" * 60)

    # モックモードでテスト
    from modules.generator.llm_client import ClaudeClient
    client = ClaudeClient(use_mock=True)
    builder = ArticleBuilder(llm_client=client)

    # テーブルフォーマットのテスト
    print("\n[Stock Table]")
    print(builder.format_stock_table(stock))

    # 2段階生成のテスト
    print("\n[2-Phase Article Generation]")
    result = builder.build_article(book, stock)

    if result.is_success():
        print(f"Success! Article length: {len(result.content)} chars")
        print(f"Is Mock: {result.is_mock}")
        print("\n--- Outline ---")
        print(result.outline[:500] + "...")
        print("\n--- Article Preview ---")
        print(result.content[:800] + "...")
    else:
        print(f"Error: {result.error}")
