# CMS-like configurable parameters
BASE_BID = 100                      # 최소 입찰가
BID_STEP = 10                       # 입찰 단위
TURN_BID_TIMEOUT_SEC = 60           # 팀장 차례 제한 시간(초)
NEXT_PLAYER_DELAY_SEC = 10          # 다음 경매까지 대기(초)
PAUSE_MAX_PER_CAPTAIN = 2           # 팀장당 퍼즈 최대 횟수
PAUSE_MAX_DURATION_SEC = 5 * 60     # 퍼즈 1회 최대(초)
STRATEGY_TIME_MINUTES = 1 * 60      # 전략 타임(초)
TEAM_LIMIT = 5                      # 팀장 포함 최대 인원
ENFORCE_SINGLE_CHANNEL = True       # 하나의 채널에서만 진행
PREVIEW_DELAY_SEC = 5               # 카운트다운 기본값 (초)