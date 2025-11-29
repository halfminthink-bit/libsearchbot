import os
import requests
from dotenv import load_dotenv

# 1. .envの読み込みテスト
print("--- [1] 環境変数 (.env) チェック ---")
load_result = load_dotenv()
print(f".env loaded status: {load_result}")

calil_key = os.getenv("CALIL_APPKEY")
if calil_key:
    # セキュリティのためキーの一部だけ表示
    masked_key = calil_key[:5] + "*" * 5
    print(f"CALIL_APPKEY found: {masked_key}")
else:
    print("❌ CALIL_APPKEY is NOT set or None.")

# 2. OpenBD 接続テスト (SSLエラー等の確認)
print("\n--- [2] OpenBD 接続テスト ---")
isbn = "9784798126708"
openbd_url = f"https://api.openbd.jp/v1/get?isbn={isbn}"
try:
    print(f"Requesting: {openbd_url}")
    response = requests.get(openbd_url, timeout=10)
    print(f"Status Code: {response.status_code}")
    print(f"Response Head: {response.text[:50]}...")
except Exception as e:
    print(f"❌ Connection Error: {e}")

# 3. カーリル 接続テスト
print("\n--- [3] カーリル API テスト ---")
if calil_key:
    system_id = "Tokyo_Minato"
    calil_url = f"http://api.calil.jp/check?appkey={calil_key}&isbn={isbn}&systemid={system_id}&format=json"
    try:
        print(f"Requesting Calil...")
        response = requests.get(calil_url, timeout=10)
        print(f"Status Code: {response.status_code}")
        print(f"Response raw: {response.text}")
    except Exception as e:
        print(f"❌ Connection Error: {e}")
else:
    print("Skipping Calil test (No Key)")