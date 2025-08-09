import asyncio
import json
import os
from helius import Helius
from websockets.client import connect
import requests

# --- 설정 파일 로드 ---
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
        input("엔터 키를 눌러 종료합니다.")
        exit()
    return config

config = load_config()
HELIUS_API_KEY = config.get("HELIUS_API_KEY")
MY_WALLET = config.get("SOLANA_WALLET")
TELEGRAM_TOKEN = config.get("TELEGRAM_TOKEN")
CHAT_ID = config.get("CHAT_ID")

# 알림을 받을 최소 달러 가치
MIN_USD_VALUE = 280.0

if not all([HELIUS_API_KEY, MY_WALLET, TELEGRAM_TOKEN, CHAT_ID]):
    print("오류: config.txt 파일의 모든 값이 제대로 입력되었는지 확인하세요.")
    input("엔터 키를 눌러 종료합니다.")
    exit()

# Helius 클라이언트 초기화
helius_client = Helius(HELIUS_API_KEY)

# --- 텔레그램 메시지 전송 함수 ---
def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        response = requests.post(url, json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"})
        if response.status_code == 200:
            print("텔레그램 메시지 전송 성공!")
        else:
            print(f"텔레그램 메시지 전송 실패: {response.text}")
    except Exception as e:
        print(f"텔레그램 메시지 전송 중 오류 발생: {e}")

# --- 메인 로직 ---
async def process_transaction(signature):
    try:
        print(f"[{signature[:6]}] 신규 거래 감지. 상세 내역 분석 시작...")
        tx = helius_client.get_transaction(tx=signature)

        if not tx:
            return

        received_asset = None

        # 1. 내 지갑으로 '수신'된 거래인지 확인
        # SOL 수신 확인
        for inst in tx.native_transfers:
            if inst.to_user_account == MY_WALLET and inst.from_user_account != MY_WALLET:
                received_asset = {
                    "type": "SOL",
                    "amount": inst.amount / 10**9, # Lamports to SOL
                    "mint": "So11111111111111111111111111111111111111112"
                }
                print(f"[{signature[:6]}] SOL 수신 확인: {received_asset['amount']} SOL")
                break
        
        # 토큰 수신 확인
        if not received_asset:
            for inst in tx.token_transfers:
                if inst.to_user_account == MY_WALLET and inst.from_user_account != MY_WALLET:
                    token_info = next((t for t in tx.token_transfers if t.mint == inst.mint), None)
                    decimals = token_info.token_standard.split('.')[0].count('0') if token_info else 6 # 기본값 6
                    
                    received_asset = {
                        "type": "Token",
                        "amount": inst.token_amount,
                        "mint": inst.mint
                    }
                    print(f"[{signature[:6]}] 토큰 수신 확인: {received_asset['amount']}개, CA: {received_asset['mint'][:6]}")
                    break
        
        # 수신된 자산이 없으면 함수 종료
        if not received_asset:
            print(f"[{signature[:6]}] 내가 보냈거나, 수신 거래가 아니므로 분석을 종료합니다.")
            return

        # 2. 수신된 자산의 달러 가치 계산
        print(f"[{signature[:6]}] 수신된 자산의 달러 가치 계산 중...")
        price_info = helius_client.get_price(mints=[received_asset["mint"]])
        if not price_info or not price_info.get(received_asset["mint"]):
            print(f"[{signature[:6]}] 가격 정보를 가져올 수 없어 알림을 보내지 않습니다.")
            return
            
        current_price = price_info[received_asset["mint"]].price
        total_usd_value = received_asset["amount"] * current_price
        
        print(f"[{signature[:6]}] 현재 시세: ${current_price:,.4f}, 총 가치: ${total_usd_value:,.2f}")

        # 3. 계산된 가치가 설정된 최소 금액 이상인지 확인
        if total_usd_value >= MIN_USD_VALUE:
            print(f"[{signature[:6]}] 설정된 최소 가치(${MIN_USD_VALUE}) 이상이므로 알림을 전송합니다.")
            
            # 토큰 Ticker 정보 가져오기
            ticker = "SOL"
            if received_asset["type"] == "Token":
                token_meta = helius_client.get_token_metadata(mints=[received_asset["mint"]])
                if token_meta:
                    ticker = token_meta[0].symbol

            # 텔레그램 메시지 조합 및 전송
            solscan_link = f"https://solscan.io/tx/{signature}"
            message = (
                f"✅ **고액 입금 알림 (${total_usd_value:,.2f})**\n\n"
                f"- **수신 토큰:** {ticker}\n"
                f"- **수신 수량:** {received_asset['amount']}\n\n"
                f"[Solscan에서 확인]({solscan_link})"
            )
            send_telegram_message(message)
        else:
            print(f"[{signature[:6]}] 설정된 최소 가치보다 작으므로 알림을 보내지 않습니다.")

    except Exception as e:
        print(f"거래 처리 중 오류 발생: {e}")


# --- 웹소켓 리스너 (이전과 동일) ---
async def listen():
    print("솔라나 지갑 감시를 시작합니다. (수신 및 금액 필터 버전)")
    RPC_URL = f"wss://mainnet.helius-rpc.com/?api-key={HELIUS_API_KEY}"
    async with connect(RPC_URL) as ws:
        await ws.send(json.dumps({
            "jsonrpc": "2.0",
            "id": 1,
            "method": "accountSubscribe",
            "params": [
                MY_WALLET,
                {"encoding": "jsonParsed", "commitment": "finalized"}
            ]
        }))
        await ws.recv() # 구독 확인 메시지
        print("연결 성공! 거래 알림을 기다립니다.")

        while True:
            try:
                message = await ws.recv()
                data = json.loads(message)
                
                if data.get("params", {}).get("result", {}).get("value", {}).get("transaction", {}):
                    signature = data["params"]["result"]["value"]["transaction"]["signatures"][0]
                    asyncio.create_task(process_transaction(signature))

            except Exception as e:
                print(f"웹소켓 오류 발생: {e}")
                await asyncio.sleep(5)

if __name__ == "__main__":
    try:
        asyncio.run(listen())
    except KeyboardInterrupt:
        print("\n프로그램을 종료합니다.")
