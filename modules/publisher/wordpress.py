"""
WordPress Publisher
生成した記事をWordPressに自動投稿するモジュール

機能:
- YAML Front Matterからメタデータを読み取り
- 画像のアップロード（アイキャッチ設定）
- カテゴリー・タグの自動設定
- 記事の投稿
"""

import os
import glob
import base64
import requests
from typing import Optional, List, Dict, Any
from dataclasses import dataclass

from dotenv import load_dotenv
load_dotenv(override=True)

try:
    import frontmatter
except ImportError:
    frontmatter = None
    print("Warning: python-frontmatter not installed. Run: pip install python-frontmatter")


@dataclass
class PublishResult:
    """投稿結果を格納するデータクラス"""
    success: bool
    post_id: Optional[int] = None
    post_url: Optional[str] = None
    error: Optional[str] = None
    filepath: Optional[str] = None


class WordPressPublisher:
    """WordPress REST API を使用した記事投稿クラス"""

    # ジャンルからカテゴリーへのマッピング
    GENRE_CATEGORY_MAP = {
        "ビジネス・経済・就職": "ビジネス・経済",
        "ビジネス・経済": "ビジネス・経済",
        "小説・エッセイ": "小説・エッセイ",
        "人文・思想・社会": "人文・思想",
        "人文・思想": "人文・思想",
    }

    def __init__(
        self,
        site_url: Optional[str] = None,
        username: Optional[str] = None,
        app_password: Optional[str] = None,
        use_mock: bool = False
    ):
        """
        Args:
            site_url: WordPressサイトのURL（例: https://example.com）
            username: WordPressユーザー名
            app_password: アプリケーションパスワード
            use_mock: モックモードを使用するか
        """
        self.site_url = (site_url or os.getenv("WP_SITE_URL", "")).rstrip("/")
        self.username = username or os.getenv("WP_USERNAME", "")
        self.app_password = app_password or os.getenv("WP_APP_PASSWORD", "")
        self.use_mock = use_mock

        # 認証ヘッダーを構築
        if self.username and self.app_password:
            credentials = f"{self.username}:{self.app_password}"
            token = base64.b64encode(credentials.encode()).decode()
            self.auth_header = {"Authorization": f"Basic {token}"}
        else:
            self.auth_header = {}

        # APIエンドポイント
        self.api_base = f"{self.site_url}/wp-json/wp/v2"

        # カテゴリー・タグのキャッシュ
        self._category_cache: Dict[str, int] = {}
        self._tag_cache: Dict[str, int] = {}

    def is_configured(self) -> bool:
        """WordPress接続が設定されているかチェック"""
        return bool(self.site_url and self.username and self.app_password)

    def _upload_media(self, image_url: str, filename: str) -> Optional[int]:
        """
        画像をWordPressメディアライブラリにアップロードする

        Args:
            image_url: 画像のURL
            filename: 保存時のファイル名

        Returns:
            Optional[int]: アップロードされたメディアのID（失敗時はNone）
        """
        if self.use_mock:
            print(f"    [Mock] Would upload image: {image_url}")
            return 12345  # モックID

        if not image_url:
            return None

        try:
            # 画像をダウンロード
            response = requests.get(image_url, timeout=30)
            response.raise_for_status()
            image_data = response.content

            # Content-Typeを推測
            content_type = response.headers.get("Content-Type", "image/jpeg")

            # WordPressにアップロード
            headers = {
                **self.auth_header,
                "Content-Type": content_type,
                "Content-Disposition": f'attachment; filename="{filename}"',
            }

            upload_response = requests.post(
                f"{self.api_base}/media",
                headers=headers,
                data=image_data,
                timeout=60
            )
            upload_response.raise_for_status()
            media_data = upload_response.json()

            return media_data.get("id")

        except requests.exceptions.RequestException as e:
            print(f"    Warning: Image upload failed: {e}")
            return None
        except Exception as e:
            print(f"    Warning: Unexpected error during image upload: {e}")
            return None

    def _resolve_category(self, genre: str) -> Optional[int]:
        """
        ジャンル名からカテゴリーIDを取得（なければ作成）

        Args:
            genre: ジャンル名

        Returns:
            Optional[int]: カテゴリーID
        """
        if not genre:
            return None

        # マッピングを適用
        category_name = self.GENRE_CATEGORY_MAP.get(genre, genre)

        # キャッシュを確認
        if category_name in self._category_cache:
            return self._category_cache[category_name]

        if self.use_mock:
            print(f"    [Mock] Would resolve category: {category_name}")
            self._category_cache[category_name] = 1
            return 1

        try:
            # 既存カテゴリーを検索
            response = requests.get(
                f"{self.api_base}/categories",
                headers=self.auth_header,
                params={"search": category_name, "per_page": 100},
                timeout=10
            )
            response.raise_for_status()
            categories = response.json()

            # 完全一致を探す
            for cat in categories:
                if cat.get("name") == category_name:
                    self._category_cache[category_name] = cat["id"]
                    return cat["id"]

            # なければ作成
            create_response = requests.post(
                f"{self.api_base}/categories",
                headers={**self.auth_header, "Content-Type": "application/json"},
                json={"name": category_name},
                timeout=10
            )
            create_response.raise_for_status()
            new_cat = create_response.json()
            self._category_cache[category_name] = new_cat["id"]
            return new_cat["id"]

        except Exception as e:
            print(f"    Warning: Category resolution failed: {e}")
            return None

    def _resolve_tags(self, tags: List[str]) -> List[int]:
        """
        タグ名のリストからタグIDのリストを取得（なければ作成）

        Args:
            tags: タグ名のリスト

        Returns:
            List[int]: タグIDのリスト
        """
        if not tags:
            return []

        tag_ids = []

        for tag_name in tags:
            if not tag_name:
                continue

            # キャッシュを確認
            if tag_name in self._tag_cache:
                tag_ids.append(self._tag_cache[tag_name])
                continue

            if self.use_mock:
                print(f"    [Mock] Would resolve tag: {tag_name}")
                self._tag_cache[tag_name] = len(self._tag_cache) + 1
                tag_ids.append(self._tag_cache[tag_name])
                continue

            try:
                # 既存タグを検索
                response = requests.get(
                    f"{self.api_base}/tags",
                    headers=self.auth_header,
                    params={"search": tag_name, "per_page": 100},
                    timeout=10
                )
                response.raise_for_status()
                existing_tags = response.json()

                # 完全一致を探す
                found = False
                for tag in existing_tags:
                    if tag.get("name") == tag_name:
                        self._tag_cache[tag_name] = tag["id"]
                        tag_ids.append(tag["id"])
                        found = True
                        break

                if not found:
                    # なければ作成
                    create_response = requests.post(
                        f"{self.api_base}/tags",
                        headers={**self.auth_header, "Content-Type": "application/json"},
                        json={"name": tag_name},
                        timeout=10
                    )
                    create_response.raise_for_status()
                    new_tag = create_response.json()
                    self._tag_cache[tag_name] = new_tag["id"]
                    tag_ids.append(new_tag["id"])

            except Exception as e:
                print(f"    Warning: Tag resolution failed for '{tag_name}': {e}")

        return tag_ids

    def _convert_markdown_to_html(self, markdown_content: str) -> str:
        """
        MarkdownをHTML（またはGutenbergブロック）に変換

        Note: 簡易的な変換のみ。本格的にはmarkdownライブラリを使用推奨。
        """
        # WordPressはMarkdownをそのまま受け付けることも多いが、
        # 基本的なHTML変換を行う
        import re

        html = markdown_content

        # 見出し変換
        html = re.sub(r'^### (.+)$', r'<h3>\1</h3>', html, flags=re.MULTILINE)
        html = re.sub(r'^## (.+)$', r'<h2>\1</h2>', html, flags=re.MULTILINE)
        html = re.sub(r'^# (.+)$', r'<h1>\1</h1>', html, flags=re.MULTILINE)

        # 太字
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html)

        # リンク
        html = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<a href="\2">\1</a>', html)

        # 段落
        paragraphs = html.split('\n\n')
        processed = []
        for p in paragraphs:
            p = p.strip()
            if p and not p.startswith('<'):
                # テーブルやHTMLタグでなければ段落で囲む
                if not p.startswith('|') and not p.startswith('*') and not p.startswith('-'):
                    p = f'<p>{p}</p>'
            processed.append(p)
        html = '\n\n'.join(processed)

        return html

    def publish_file(self, filepath: str, status: str = "draft") -> PublishResult:
        """
        Markdownファイルを読み込んでWordPressに投稿する

        Args:
            filepath: Markdownファイルのパス
            status: 投稿ステータス（"draft", "publish", "pending"）

        Returns:
            PublishResult: 投稿結果
        """
        if frontmatter is None:
            return PublishResult(
                success=False,
                error="python-frontmatter is not installed",
                filepath=filepath
            )

        try:
            # Front Matterを読み込み
            with open(filepath, "r", encoding="utf-8") as f:
                post = frontmatter.load(f)

            metadata = post.metadata
            content = post.content

            title = metadata.get("title", "無題")
            isbn = metadata.get("isbn", "")
            image_url = metadata.get("image_url", "")
            genre = metadata.get("genre", "")
            region = metadata.get("region", "")
            author = metadata.get("author", "")

            print(f"    Title: {title}")
            print(f"    Genre: {genre}, Region: {region}")

            # 画像アップロード
            media_id = None
            if image_url:
                print(f"    Uploading featured image...")
                media_id = self._upload_media(image_url, f"isbn_{isbn}.jpg")
                if media_id:
                    print(f"    Image uploaded: ID={media_id}")

            # カテゴリー解決
            category_id = self._resolve_category(genre)
            categories = [category_id] if category_id else []

            # タグ解決（地域と著者をタグに）
            tag_names = []
            if region:
                tag_names.append(region)
            if author:
                tag_names.append(author)
            tag_ids = self._resolve_tags(tag_names)

            # 投稿
            return self._create_post(
                title=title,
                content=content,
                status=status,
                featured_media=media_id,
                categories=categories,
                tags=tag_ids,
                filepath=filepath
            )

        except Exception as e:
            return PublishResult(
                success=False,
                error=str(e),
                filepath=filepath
            )

    def _create_post(
        self,
        title: str,
        content: str,
        status: str = "draft",
        featured_media: Optional[int] = None,
        categories: Optional[List[int]] = None,
        tags: Optional[List[int]] = None,
        filepath: Optional[str] = None
    ) -> PublishResult:
        """
        WordPress REST APIで記事を作成する

        Args:
            title: 記事タイトル
            content: 記事本文（Markdown）
            status: 投稿ステータス
            featured_media: アイキャッチ画像のメディアID
            categories: カテゴリーIDリスト
            tags: タグIDリスト
            filepath: 元ファイルのパス（参照用）

        Returns:
            PublishResult: 投稿結果
        """
        if self.use_mock:
            print(f"    [Mock] Would create post: {title}")
            print(f"    [Mock] Status: {status}, Categories: {categories}, Tags: {tags}")
            return PublishResult(
                success=True,
                post_id=99999,
                post_url=f"{self.site_url}/?p=99999",
                filepath=filepath
            )

        if not self.is_configured():
            return PublishResult(
                success=False,
                error="WordPress credentials not configured",
                filepath=filepath
            )

        try:
            # HTMLに変換（オプション）
            html_content = self._convert_markdown_to_html(content)

            post_data = {
                "title": title,
                "content": html_content,
                "status": status,
            }

            if featured_media:
                post_data["featured_media"] = featured_media
            if categories:
                post_data["categories"] = categories
            if tags:
                post_data["tags"] = tags

            response = requests.post(
                f"{self.api_base}/posts",
                headers={**self.auth_header, "Content-Type": "application/json"},
                json=post_data,
                timeout=30
            )
            response.raise_for_status()
            result = response.json()

            return PublishResult(
                success=True,
                post_id=result.get("id"),
                post_url=result.get("link"),
                filepath=filepath
            )

        except requests.exceptions.RequestException as e:
            return PublishResult(
                success=False,
                error=f"API request failed: {e}",
                filepath=filepath
            )
        except Exception as e:
            return PublishResult(
                success=False,
                error=str(e),
                filepath=filepath
            )

    def publish_all(
        self,
        output_dir: str = "data/output",
        status: str = "draft",
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        指定ディレクトリ内の全Markdownファイルを投稿する

        Args:
            output_dir: 出力ディレクトリ
            status: 投稿ステータス
            limit: 投稿数の上限

        Returns:
            Dict: 投稿結果のサマリー
        """
        pattern = os.path.join(output_dir, "*.md")
        files = sorted(glob.glob(pattern))

        if limit:
            files = files[:limit]

        results = {
            "total": len(files),
            "success": 0,
            "failed": 0,
            "posts": []
        }

        for filepath in files:
            filename = os.path.basename(filepath)
            print(f"  Publishing: {filename}")

            result = self.publish_file(filepath, status=status)

            if result.success:
                results["success"] += 1
                print(f"    -> Success: {result.post_url}")
            else:
                results["failed"] += 1
                print(f"    -> Failed: {result.error}")

            results["posts"].append({
                "filepath": filepath,
                "success": result.success,
                "post_id": result.post_id,
                "post_url": result.post_url,
                "error": result.error
            })

        return results


# 単体テスト用
if __name__ == "__main__":
    print("Testing WordPressPublisher")
    print("=" * 60)

    publisher = WordPressPublisher(use_mock=True)

    print(f"\nConfigured: {publisher.is_configured()}")
    print(f"Site URL: {publisher.site_url}")

    # モックテスト
    print("\n[Mock Publish Test]")
    result = publisher._create_post(
        title="テスト記事",
        content="# テスト\n\nこれはテストです。",
        status="draft"
    )
    print(f"Result: {result}")
