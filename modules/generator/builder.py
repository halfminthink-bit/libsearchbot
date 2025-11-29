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
STOCK_TABLE_PLACEHOLDER = "[[STOCK_TABLE]]"
PROMO_BOX_PLACEHOLDER = "[[PROMO_BOX]]"


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
    # メタデータ（WordPress投稿用）
    title: Optional[str] = None
    isbn: Optional[str] = None
    image_url: Optional[str] = None
    genre: Optional[str] = None
    region: Optional[str] = None
    author: Optional[str] = None

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
            # フェイルセーフ: 蔵書情報がない場合は「予約殺到中」として収益化につなげる
            lines = [
                "| 図書館名 | 貸出状況 | 予約 |",
                "|---|---|---|",
                "| 全館 | 🔴 貸出不可/調査中 | [確認](https://calil.jp/) |",
                "",
                "※人気のため予約が殺到しているか、システム反映待ちの可能性があります。",
                "**今すぐ読みたい方は電子書籍がおすすめです！**"
            ]
            return "\n".join(lines)

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

    def _generate_simple_stock_table(self, stock_result: StockResult) -> str:
        """
        シンプルで清潔感のあるHTML在庫テーブルを生成

        Args:
            stock_result: 蔵書検索結果

        Returns:
            str: HTMLテーブル文字列
        """
        if not stock_result.libraries:
            # フェイルセーフ: 蔵書情報がない場合
            return """<div style="border: 1px solid #dee2e6; border-radius: 4px; padding: 16px; margin: 20px 0; background-color: #fff3cd; border-color: #ffc107;">
<table style="width: 100%; border-collapse: collapse; margin: 0;">
  <thead>
    <tr style="background-color: #f8f9fa; border-bottom: 2px solid #dee2e6;">
      <th style="padding: 12px; text-align: left; font-weight: 600; color: #212529;">図書館名</th>
      <th style="padding: 12px; text-align: left; font-weight: 600; color: #212529;">貸出状況</th>
      <th style="padding: 12px; text-align: left; font-weight: 600; color: #212529;">予約</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td style="padding: 12px; border-bottom: 1px solid #dee2e6;">全館</td>
      <td style="padding: 12px; border-bottom: 1px solid #dee2e6; color: #dc3545;">🔴 貸出不可/調査中</td>
      <td style="padding: 12px; border-bottom: 1px solid #dee2e6;"><a href="https://calil.jp/" target="_blank" rel="noopener" style="color: #0056b3; text-decoration: none;">確認</a></td>
    </tr>
  </tbody>
</table>
<p style="margin-top: 12px; margin-bottom: 0; font-size: 0.9em; color: #856404;">※人気のため予約が殺到しているか、システム反映待ちの可能性があります。<br><strong>今すぐ読みたい方は電子書籍がおすすめです！</strong></p>
</div>"""

        # テーブル行を生成
        rows = []
        for lib in stock_result.libraries:
            status_emoji = self._get_status_emoji(lib.status)
            status_color = "#28a745" if lib.status == "貸出可" else "#dc3545" if lib.status == "貸出中" else "#6c757d"
            
            reserve_cell = "-"
            if lib.status != "蔵書なし" and lib.reserve_url:
                reserve_cell = f'<a href="{lib.reserve_url}" target="_blank" rel="noopener" style="color: #0056b3; text-decoration: none;">予約する</a>'
            
            rows.append(f'''    <tr>
      <td style="padding: 12px; border-bottom: 1px solid #dee2e6;">{lib.library_name}</td>
      <td style="padding: 12px; border-bottom: 1px solid #dee2e6; color: {status_color};">{status_emoji} {lib.status}</td>
      <td style="padding: 12px; border-bottom: 1px solid #dee2e6;">{reserve_cell}</td>
    </tr>''')

        # サマリー
        available_count = sum(1 for lib in stock_result.libraries if lib.status == "貸出可")
        total_count = len(stock_result.libraries)
        summary = f'<p style="margin-top: 12px; margin-bottom: 0; font-size: 0.9em; color: #495057;"><strong>{total_count}館中 {available_count}館で貸出可能</strong> （調査時点）</p>'

        return f'''<div style="border: 1px solid #dee2e6; border-radius: 4px; padding: 16px; margin: 20px 0; background-color: #ffffff;">
<table style="width: 100%; border-collapse: collapse; margin: 0;">
  <thead>
    <tr style="background-color: #f8f9fa; border-bottom: 2px solid #dee2e6;">
      <th style="padding: 12px; text-align: left; font-weight: 600; color: #212529;">図書館名</th>
      <th style="padding: 12px; text-align: left; font-weight: 600; color: #212529;">貸出状況</th>
      <th style="padding: 12px; text-align: left; font-weight: 600; color: #212529;">予約</th>
    </tr>
  </thead>
  <tbody>
{chr(10).join(rows)}
  </tbody>
</table>
{summary}
</div>'''

    def _generate_simple_promo_box(
        self,
        kindle_url: str,
        audible_url: str,
        is_stock_scarce: bool = False
    ) -> str:
        """
        ミニマルで洗練されたアフィリエイト誘導ブロックを生成

        Args:
            kindle_url: Kindle UnlimitedのURL
            audible_url: AudibleのURL
            is_stock_scarce: 在庫が逼迫しているかどうか

        Returns:
            str: HTMLブロック文字列
        """
        if is_stock_scarce:
            message = "現在、図書館では予約待ちが発生しています。<br>お急ぎの方は、在庫切れのない電子書籍での読書がおすすめです。"
            badge = '<span style="background-color: #FFF4E6; color: #D97706; font-size: 0.8em; padding: 2px 8px; border-radius: 4px; border: 1px solid #FCD34D; font-weight: bold; vertical-align: middle; margin-left: 8px;">予約待ち対策</span>'
        else:
            message = "「返却期限を気にせずゆっくり読みたい」という方は、電子書籍版もおすすめです。"
            badge = ""

        return f'''<div style="border: 1px solid #e5e7eb; border-radius: 8px; padding: 24px; margin: 32px 0; background-color: #ffffff;">
  <h3 style="margin-top: 0; margin-bottom: 16px; font-size: 1.1em; color: #111827; font-weight: 700; border-bottom: none; display: flex; align-items: center;">
    📖 今すぐ読むなら {badge}
  </h3>
  <p style="margin-bottom: 20px; color: #4b5563; line-height: 1.7; font-size: 0.95em;">{message}</p>
  
  <div style="display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 16px;">
    <a href="{kindle_url}" target="_blank" rel="noopener" style="flex: 1; min-width: 200px; display: inline-flex; align-items: center; justify-content: center; padding: 14px 20px; background-color: #FF9900; color: white; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 0.95em; transition: opacity 0.2s;">
      📚 Kindle Unlimited (30日無料)
    </a>
    <a href="{audible_url}" target="_blank" rel="noopener" style="flex: 1; min-width: 200px; display: inline-flex; align-items: center; justify-content: center; padding: 14px 20px; background-color: #232F3E; color: white; text-decoration: none; border-radius: 6px; font-weight: 700; font-size: 0.95em; transition: opacity 0.2s;">
      🎧 Audibleで聴く (30日無料)
    </a>
  </div>
  
  <p style="margin-bottom: 0; font-size: 0.85em; color: #9ca3af; text-align: right;">※無料期間中に解約すれば料金はかかりません</p>
</div>'''

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
            description=book_info.description[:500] if book_info.description else "情報なし",
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
        outline: str
    ) -> LLMResponse:
        """
        記事本文を生成する（Phase 2）
        AIはテキスト部分のみ生成し、HTMLパーツは後からPythonで挿入

        Args:
            book_info: 書籍情報
            region_name: 地域名
            outline: アウトライン

        Returns:
            LLMResponse: 生成された記事本文（プレースホルダー含む）
        """
        # Jinja2テンプレートを読み込み
        template = self.jinja_env.get_template("draft_prompt.j2")

        # プロンプトをレンダリング（シンプルに）
        prompt = template.render(
            book_title=book_info.title or "不明",
            author=book_info.author or "不明",
            description=book_info.description[:500] if book_info.description else "情報なし",
            region_name=region_name
        )

        # モックモードの場合
        if self.llm_client.use_mock:
            mock_article = f"""{region_name}の図書館で『{book_info.title or "書籍タイトル"}』を借りよう！無料で読める場所と在庫情報
---
この本を無料で読みたいという方に、図書館での在庫状況をご案内します。
---
この本は、多くの読者から支持されている人気作です。図書館でも常に貸出中で、予約待ちになることが多い一冊です。
"""
            return LLMResponse(
                content=mock_article,
                model="mock",
                is_mock=True
            )

        # LLMで記事生成
        return self.llm_client.generate(
            prompt=prompt,
            system_prompt="あなたは図書館のベテラン司書です。",
            temperature=0.7,
            max_tokens=8192
        )

    def build_article(
        self,
        book_info: BookInfo,
        stock_result: StockResult,
        region_name: Optional[str] = None,
        use_mock: bool = False,
        genre_label: Optional[str] = None
    ) -> BuildResult:
        """
        記事を生成する（2段階生成のオーケストレーター）

        Args:
            book_info: 書籍情報
            stock_result: 蔵書検索結果
            region_name: 地域名（省略時はシステムIDから推測）
            use_mock: モックモードを使用するか
            genre_label: ジャンルラベル（例: "ビジネス・経済"）

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

        # Phase 2: 記事本文生成（AIはテキスト部分のみ生成）
        print("    Phase 2: 記事本文生成中...")
        draft_response = self.create_draft(
            book_info,
            region_name,
            outline_response.content
        )

        if not draft_response.is_success():
            return BuildResult(
                content="",
                outline=outline_response.content,
                error=f"Draft generation failed: {draft_response.error}"
            )

        total_input_tokens += draft_response.input_tokens
        total_output_tokens += draft_response.output_tokens

        # 在庫逼迫度を計算
        is_stock_scarce = self._calculate_scarcity(stock_result) if stock_result else False

        # アフィリエイト関連の環境変数を取得
        affiliate_tag = os.getenv("AMAZON_AFFILIATE_TAG", "mytag-22")
        kindle_url = os.getenv("KINDLE_PROMO_URL", f"https://www.amazon.co.jp/kindle-dbs/hz/signup?tag={affiliate_tag}")
        audible_url = os.getenv("AUDIBLE_PROMO_URL", f"https://www.amazon.co.jp/hz/audible/mlp?tag={affiliate_tag}")

        # Python側でHTMLパーツを生成
        stock_html = self._generate_simple_stock_table(stock_result)
        promo_html = self._generate_simple_promo_box(kindle_url, audible_url, is_stock_scarce)

        # AI出力を `---` で分割
        parts = draft_response.content.split("---")
        
        # パーツを抽出（空白行を除去）
        h1_title = ""
        intro_text = ""
        review_text = ""
        
        if len(parts) >= 3:
            h1_title = parts[0].strip().replace("# ", "").strip()  # 念のため#除去
            intro_text = parts[1].strip()
            review_text = parts[2].strip()
        elif len(parts) == 2:
            # 2パーツしかない場合（フォールバック）
            h1_title = parts[0].strip().replace("# ", "").strip()
            intro_text = parts[1].strip()
            review_text = ""
        else:
            # 分割失敗時のフォールバック
            h1_title = f"【{region_name}】『{book_info.title}』の在庫がある図書館・貸出状況まとめ"
            intro_text = draft_response.content
            review_text = ""

        # 記事タイトルを設定
        article_title = h1_title if h1_title else f"【{region_name}】『{book_info.title}』の在庫がある図書館・貸出状況まとめ"

        # 記事を組み立て（結合）
        final_content = f"""# {h1_title}

{intro_text}

## {region_name}の図書館在庫・貸出状況
{stock_html}

## この本が「予約殺到」する理由
{review_text}

{promo_html}
"""

        return BuildResult(
            content=final_content,
            outline=outline_response.content,
            is_mock=outline_response.is_mock or draft_response.is_mock,
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            # メタデータ
            title=article_title,
            isbn=book_info.isbn,
            image_url=book_info.cover_url,
            genre=genre_label,
            region=region_name,
            author=book_info.author
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

    def save_article_with_frontmatter(self, result: BuildResult, filepath: str) -> bool:
        """
        YAML Front Matter付きで記事をファイルに保存する

        Args:
            result: ビルド結果（メタデータ含む）
            filepath: 保存先のファイルパス

        Returns:
            bool: 保存成功かどうか
        """
        try:
            # ディレクトリがなければ作成
            os.makedirs(os.path.dirname(filepath), exist_ok=True)

            # YAML Front Matterを構築
            frontmatter_lines = [
                "---",
                f"title: \"{result.title or ''}\"",
                f"isbn: \"{result.isbn or ''}\"",
                f"image_url: \"{result.image_url or ''}\"",
                f"genre: \"{result.genre or ''}\"",
                f"region: \"{result.region or ''}\"",
                f"author: \"{result.author or ''}\"",
                "---",
                "",
            ]
            frontmatter = "\n".join(frontmatter_lines)

            # Front Matter + 本文を結合
            full_content = frontmatter + result.content

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(full_content)
            return True
        except Exception as e:
            print(f"Error saving article with frontmatter: {e}")
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
