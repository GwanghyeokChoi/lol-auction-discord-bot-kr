# lol-auction-discord-bot-kr (Modular CMS-style)

명령어/모델/서비스로 분리된 구조. `.env`로 토큰 주입.

## 구조
- `bot.py` — 진입점(봇 초기화/코그 로드)
- `commands/auction.py` — 명령어 레이어
- `services/auction_service.py` — 비즈니스 로직(경매 상태/로직)
- `models/entities.py` — 데이터 모델 (Player/Captain/Team/AuctionState)
- `utils/format.py` — 공통 포맷/파서
- `config.py` — 설정값(CMS 스타일의 파라미터)

## 실행
```bash
pip install -r requirements.txt
cp .env.example .env   # Windows: copy .env.example .env
# .env에 DISCORD_TOKEN 넣기
python bot.py
```

## 주요 명령
- `!팀장 등록 팀명;이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]`
- `!경매자 등록` (+ CSV 첨부) 또는 `!경매자 등록 이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]`
- `!경매 시작 <팀수> <팀장초기포인트>`
- `!입찰 <포인트>` / `!패스` / `!퍼즈` / `!퍼즈 종료`
- 조회: `!경매자 조회 [닉]`, `!팀원 조회 <팀장닉>`, `!경매순서조회`, `!유찰자조회`, `!포인트 확인 <팀명>`
- 결과: `!파일 내보내기`
