LibSearchBot - 実装仕様書
プロジェクト名: LibSearchBot 目的: カーリルAPIを活用し、書籍の蔵書状況と最寄り図書館情報を網羅したSEO記事を完全自動生成する。 フェーズ:

Phase 1 (MVP): CSV入力（ISBN×地域）に基づき記事を生成・保存。

Phase 2 (Automation): DBによる状態管理、WordPress自動投稿、新刊情報の自動取得。

本ドキュメントでは、Phase 1の実装およびPhase 2を見据えたアーキテクチャ構築を指示する。

1. システムアーキテクチャ
車中泊メディア用ボット（ArticleBot v4）のアーキテクチャを踏襲し、モジュール構成を採用する。

libsearchbot/
├── main.py                     # エントリーポイント
├── .env                        # APIキー管理 (CALIL_APPKEY, OPENAI/ANTHROPIC_KEY)
├── config.yaml                 # 全体設定
├── core/
│   ├── database.py             # SQLite管理 (Phase 2用だが初期から枠組み作成)
│   └── orchestrator.py         # 処理パイプライン制御
├── modules/
│   ├── strategist/             # ターゲット選定
│   │   └── csv_loader.py       # ISBN, 地域コードのCSV読み込み
│   ├── collector/              # 情報収集
│   │   ├── calil_api.py        # カーリルAPI (蔵書・図書館情報)
│   │   └── openbd_api.py       # OpenBD API (書誌情報・書影)
│   ├── generator/              # 記事生成
│   │   ├── llm_client.py       # Claude/OpenAI Client
│   │   └── builder.py          # プロンプト組立・Markdown生成
│   └── publisher/              # 出力・投稿
│       └── wordpress.py        # WordPress投稿 (Phase 2)
└── data/
    ├── input/                  # 入力CSV (target_books.csv)
    └── output/                 # 生成記事 (Markdown)
2. データフロー (Phase 1)
CSV入力: isbn, city_code (カーリルのシステムID), keyword を読み込む。

情報収集 (Collector):

OpenBD API: ISBNから書名、著者、あらすじ、書影URLを取得。

Calil API (Library): 指定地域の図書館リスト、住所、開館情報を取得。

Calil API (Check): 該当ISBNのその地域での貸出可否を取得（※ポーリング処理が必要）。

記事構成 (Generator):

収集したデータを構造化テキストに変換。

LLM（Claude）にデータを渡し、SEO記事を執筆させる。

重要: 在庫状況はLLMに「創作」させず、APIから得た結果をMarkdownのテーブルとしてそのまま埋め込むこと。

出力: Markdownファイルとして保存。

3. モジュール詳細要件
3.1. Collector: calil_api.py
カーリルAPIは非同期（ポーリング）な挙動をするため、以下のロジックを実装すること。

API: http://api.calil.jp/check

処理フロー:

リクエスト送信（appkey, isbn, systemid）。

レスポンスの continue 値を確認。

continue=1 の場合、2秒待機して再リクエスト（最大5回）。

continue=0 になったら確定データを取得。

取得データ: 図書館名、貸出状況（貸出可/貸出中/蔵書なし/予約受付中）。

3.2. Collector: openbd_api.py
書誌情報（タイトル、著者、内容紹介）と書影（表紙画像）を取得する。会員登録不要のOpenBDを使用。

API: https://api.openbd.jp/v1/get

用途: 記事の導入部、書影表示、Amazon/Kindleアフィリエイトリンク生成用。

3.3. Generator: builder.py
SEOに強い記事構成を作成する。

ペルソナ: 「地元の図書館事情に詳しいベテラン司書兼ブックガイド」。

記事構成テンプレート:

導入: 本の魅力と「無料で読むなら図書館」という訴求。

在庫状況テーブル: カーリルAPIの結果を表で表示（※ここはPython側でHTML/Markdownテーブルを生成し、LLMの出力に挿入する形をとる）。

図書館ガイド: 対象地域の図書館の場所、アクセス、特徴（自習室有無など）。

借りられなかった場合: Kindle UnlimitedやAmazon購入への誘導（マネタイズ）。

3.4. Monetization Logic
APIで「在庫なし」または「貸出中」が多い場合、Amazon購入リンクのボタンを強調するロジックを組み込む。

「今すぐ読みたいならKindle Unlimited」の訴求を入れる。

4. 開発ステップ（Claude Codeへの指示）
Step 1: プロジェクトセットアップ
ディレクトリ構造の作成。

必要なライブラリ（requests, pandas, python-dotenv, anthropic）の requirements.txt 作成とインストール。

.env テンプレートの作成。

Step 2: Collectorの実装
OpenBD クラスの実装と単体テスト（ISBNを渡して書誌情報を返せるか）。

Calil クラスの実装と単体テスト（ISBNとシステムIDを渡して、在庫ステータスを返せるか）。特にポーリング処理を確実に行うこと。

Step 3: Generatorの実装
収集したデータをLLMプロンプトに埋め込むテンプレートエンジンの作成。

在庫状況をMarkdownテーブルに整形する関数の実装。

カラム: 図書館名 | 貸出状況 | 予約

Claude APIを使用した記事生成の実装。

Step 4: Main Loop (CSV Processing)
data/input/target_books.csv を読み込み、1行ずつ処理して data/output/ にMarkdownを吐き出すスクリプトの作成。

補足：アフィリエイト・SEO戦略上の指示
Amazonリンク: ASINはISBN-10とほぼ同義なので、ISBNから自動生成するロジックを入れること。

URL形式: https://www.amazon.co.jp/dp/{ISBN10}?tag={AMAZON_TAG}

キーワード戦略: 記事タイトルは「【{地域名}】『{書名}』の在庫がある図書館・貸出状況まとめ」を基本フォーマットとする。