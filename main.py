import asyncio
import json
import websockets
import requests
import os

# config.txt에서 설정값 읽어오기
def load_config(filename="config.txt"):
    config = {}
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    config[key.strip()] = value.strip()
    except FileNotFoundError:
        print(f"오류: 설정 파일({filename})을 찾을 수 없습니다.")
        print("프로그램과 같은 폴더에 config.txt 파일이 있는지 확인하세요.")
        input("엔터 키를 눌러 종료합니다.")
        exit()
    return config

config = load_config()
SOLANA_WALLET = config.get("SOLANA_WALLET")
TELEGRAM_TOKEN = config.get("TELEGRAM_TOKEN")
CHAT_ID = config.get("CHAT_ID")

if not all([SOLANA_WALLET, TELEGRAM_TOKEN, CHAT_ID]):
    print("오류: config.txt 파일에 SOLANA_WALLET, TELEGRAM_TOKEN, CHAT_ID 값이 모두 제대로 입력되었는지 확인하세요.")
    input("엔터 키를 눌러 종료합니다.")
    exit()

RPC_URL = "wss://api.mainnet-beta.solana.com"

def send_telegram_message(text):
    # 이 부분의 URL 주소 오타를 수정했습니다.
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": CHAT_ID, "text": text})
        print("텔레그램 메시지 전송 성공!")
    except Exception as e:
        print(f"텔레그램 메시지 전송 중 오류 발생: {e}")

async def listen():
    print("솔라나 지갑 감시를 시작합니다. (단순 버전)")
    async with websockets.connect(RPC_URL) as ws:
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "logsSubscribe",
            "params": [
                {"mentions": [SOLANA_WALLET]},
                {"commitment": "finalized"}
            ]
        }))
        await ws.recv()
        print("연결 성공! 거래 알림을 기다립니다.")
        while True:
            try:
                message = await ws.recv()
                data = json.loads(message)
                if "params" in data:
                    signature = data["params"]["result"]["value"]["signature"]
                    solscan_link = f"https://solscan.io/tx/{signature}"
                    print(f"새로운 거래 발견! 서명: {signature}")
                    send_telegram_message(f"💸 새 거래 발생!\n{solscan_link}")
            except Exception as e:
                print(f"오류 발생, 재연결 시도: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
