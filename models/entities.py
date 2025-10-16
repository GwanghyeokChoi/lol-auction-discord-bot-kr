from dataclasses import dataclass, field
from typing import Optional, Dict, List
import datetime

@dataclass
class Player:
    name: str
    nickname: str
    tier: str
    main_pos: str
    sub_pos: str
    most1: str
    most2: Optional[str] = None
    most3: Optional[str] = None
    status: str = "대기"  # 대기, 진행, 낙찰, 유찰
    won_team: Optional[str] = None
    won_price: Optional[int] = None

@dataclass
class Captain:
    team_name: str
    real_name: str
    nickname: str
    tier: str
    main_pos: str
    sub_pos: str
    most1: str
    most2: Optional[str] = None
    most3: Optional[str] = None
    total_pts: int = 0
    used_pts: int = 0
    pause_used: int = 0

    @property
    def remain_pts(self) -> int:
        return self.total_pts - self.used_pts

@dataclass
class Team:
    captain_nick: str
    members: List[str] = field(default_factory=list)
    limit: int = 5

    def can_add(self) -> bool:
        return len(self.members) + 1 < self.limit

@dataclass
class AuctionState:
    total_teams: int = 0
    started: bool = False
    strategy_called: bool = False
    channel_id: Optional[int] = None

    players: Dict[str, Player] = field(default_factory=dict)
    captains: Dict[str, Captain] = field(default_factory=dict)
    teams: Dict[str, Team] = field(default_factory=dict)
    captain_user_map: Dict[int, str] = field(default_factory=dict) 

    player_order: List[str] = field(default_factory=list)
    captain_order: List[str] = field(default_factory=list)
    current_player_idx: int = -1
    current_captain_idx: int = 0

    current_bid: int = 0
    current_bidder: Optional[str] = None
    paused_until: Optional[datetime.datetime] = None
    pause_owner: Optional[str] = None

    def reset_round(self):
        self.current_bid = 0
        self.current_bidder = None
        self.current_captain_idx = 0
        self.paused_until = None
        self.pause_owner = None

    def everyone_has_member(self) -> bool:
        for c_nick in self.captains.keys():
            team = self.teams.get(c_nick)
            if not team or len(team.members) == 0:
                return False
        return True
