"""
LLM クライアント
Anthropic Claude API を使用してテキスト生成を行う
"""

import os
from typing import Optional
from dataclasses import dataclass
from dotenv import load_dotenv

try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


@dataclass
class LLMResponse:
    """LLMレスポンスを格納するデータクラス"""
    content: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    is_mock: bool = False
    error: Optional[str] = None

    def is_success(self) -> bool:
        """レスポンスが成功かどうか"""
        return self.error is None and len(self.content) > 0


class ClaudeClient:
    """Anthropic Claude API クライアントクラス"""

    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    MAX_TOKENS = 4096

    # モックレスポンス用のテンプレート
    MOCK_RESPONSE_TEMPLATE = """# 『{title}』を{region}の図書館で無料で読もう！

## はじめに

こんにちは！地元の図書館事情に詳しいベテラン司書です。

今回は **『{title}』** を{region}エリアの図書館で借りる方法をご紹介します。

この本は{author}による名著で、多くの方に読まれている一冊です。

## 蔵書状況

{stock_table}

## 各図書館へのアクセス

{region}エリアには複数の図書館があり、それぞれ特色があります。お近くの図書館をぜひご利用ください。

## 借りられなかった場合は？

人気の本は貸出中のことも多いです。そんなときは：

- **予約サービス**を利用する
- **電子書籍版**をチェックする
- **購入**を検討する

Amazon等での購入リンクは以下をご参照ください。

## まとめ

『{title}』は図書館で無料で読むことができます。ぜひお近くの図書館を訪れてみてください！
"""

    def __init__(self, api_key: Optional[str] = None, use_mock: bool = False):
        """
        Args:
            api_key: Anthropic APIキー（省略時は環境変数から取得）
            use_mock: モックモードを使用するかどうか
        """
        load_dotenv(override=True)

        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self.use_mock = use_mock
        self.client = None

        if not use_mock and self.api_key and ANTHROPIC_AVAILABLE:
            self.client = anthropic.Anthropic(api_key=self.api_key)

    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: float = 0.7,
        # モック用の追加パラメータ
        mock_context: Optional[dict] = None
    ) -> LLMResponse:
        """
        プロンプトを送信してテキストを生成する

        Args:
            prompt: ユーザープロンプト
            system_prompt: システムプロンプト（省略可）
            model: 使用するモデル（省略時はデフォルト）
            max_tokens: 最大トークン数（省略時はデフォルト）
            temperature: 生成の多様性（0.0-1.0）
            mock_context: モックレスポンス生成用のコンテキスト

        Returns:
            LLMResponse: LLMのレスポンス
        """
        model = model or self.DEFAULT_MODEL
        max_tokens = max_tokens or self.MAX_TOKENS

        # モックモードの場合
        if self.use_mock:
            return self._generate_mock_response(mock_context or {}, model)

        # APIキーがない場合
        if not self.api_key:
            return LLMResponse(
                content="",
                model=model,
                error="ANTHROPIC_API_KEY is not set. Please set it in .env file or use mock mode."
            )

        # Anthropicライブラリがない場合
        if not ANTHROPIC_AVAILABLE:
            return LLMResponse(
                content="",
                model=model,
                error="anthropic library is not installed. Run: pip install anthropic"
            )

        try:
            # メッセージを作成
            messages = [{"role": "user", "content": prompt}]

            # API呼び出し
            kwargs = {
                "model": model,
                "max_tokens": max_tokens,
                "messages": messages,
                "temperature": temperature,
            }
            if system_prompt:
                kwargs["system"] = system_prompt

            response = self.client.messages.create(**kwargs)

            # レスポンスをパース
            content = ""
            for block in response.content:
                if hasattr(block, 'text'):
                    content += block.text

            return LLMResponse(
                content=content,
                model=response.model,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
                is_mock=False
            )

        except anthropic.APIError as e:
            return LLMResponse(
                content="",
                model=model,
                error=f"Anthropic API error: {e}"
            )
        except Exception as e:
            return LLMResponse(
                content="",
                model=model,
                error=f"Unexpected error: {e}"
            )

    def _generate_mock_response(self, context: dict, model: str) -> LLMResponse:
        """モックレスポンスを生成する"""
        title = context.get("title", "書籍タイトル")
        author = context.get("author", "著者名")
        region = context.get("region", "対象地域")
        stock_table = context.get("stock_table", "| 図書館名 | 状況 |\n|---|---|\n| サンプル図書館 | 貸出可 |")

        content = self.MOCK_RESPONSE_TEMPLATE.format(
            title=title,
            author=author,
            region=region,
            stock_table=stock_table
        )

        return LLMResponse(
            content=content,
            model=model,
            input_tokens=0,
            output_tokens=len(content),
            is_mock=True
        )

    def is_available(self) -> bool:
        """APIが利用可能かどうか"""
        if self.use_mock:
            return True
        return bool(self.api_key and ANTHROPIC_AVAILABLE)


# 単体テスト用
if __name__ == "__main__":
    # モックモードでテスト
    client = ClaudeClient(use_mock=True)

    print("Testing ClaudeClient (mock mode)")
    print("-" * 50)

    response = client.generate(
        prompt="テスト",
        mock_context={
            "title": "リーダブルコード",
            "author": "Dustin Boswell",
            "region": "東京都港区",
            "stock_table": "| 図書館 | 状況 |\n|---|---|\n| みなと図書館 | 貸出可 |"
        }
    )

    if response.is_success():
        print(f"Model: {response.model}")
        print(f"Is Mock: {response.is_mock}")
        print(f"Content length: {len(response.content)} chars")
        print("\nContent preview:")
        print(response.content[:500])
    else:
        print(f"Error: {response.error}")
