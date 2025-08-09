import asyncio
import json
import websockets
import requests
import os

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
HELIUS_API_KEY = config.get("HELIUS_API_KEY")
SOLANA_WALLET = config.get("SOLANA_WALLET")
TELEGRAM_TOKEN = config.get("TELEGRAM_TOKEN")
CHAT_ID = config.get("CHAT_ID")

if not all([HELIUS_API_KEY, SOLANA_WALLET, TELEGRAM_TOKEN, CHAT_ID]):
    print("오류: config.txt 파일의 모든 값이 제대로 입력되었는지 확인하세요.")
    input("엔터 키를 눌러 종료합니다.")
    exit()

RPC_URL = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"

async def listen():
    print("솔라나 지갑 감시를 시작합니다. 이 창을 끄지 마세요...")
    print(f"추적 중인 지갑 주소: {SOLANA_WALLET}")
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
        
        subscription_response = await ws.recv()
        print("연결 성공! 거래 알림을 기다립니다.")

        while True:
            try:
                message = await ws.recv()
                data = json.loads(message)

                if "params" in data and "signature" in data["params"]["result"]["value"]:
                    tx_signature = data["params"]["result"]["value"]["signature"]
                    print(f"새로운 거래 발견! 서명: {tx_signature}")
                    send_message(f"💸 새 거래 발생!\nhttps://solscan.io/tx/{tx_signature}")
            except Exception as e:
                print(f"오류 발생: {e}, 다시 연결을 시도합니다.")
                await asyncio.sleep(5)

def send_message(text):
    url = f"https.api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(url, json={"chat_id": CHAT_ID, "text": text})
        if response.status_code == 200:
            print("텔레그램 메시지 전송 성공!")
        else:
            print(f"텔레그램 메시지 전송 실패: {response.text}")
    except Exception as e:
        print(f"텔레그램 메시지 전송 중 오류 발생: {e}")

if __name__ == "__main__":
    try:
        asyncio.get_event_loop().run_until_complete(listen())
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")