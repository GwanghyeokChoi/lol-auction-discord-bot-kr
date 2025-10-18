# models/view_format.py
from __future__ import annotations

def norm(s: str) -> str:
    return (s or "").strip().lower()

def fmt_captain_line(c_nick: str, cap) -> str:
    """
    팀장: [{팀명}](팀장) 닉네임(이름) / 티어 / 주 라인 / 부 라인
    """
    team = getattr(cap, "team_name", "")
    real = getattr(cap, "real_name", "")
    tier = getattr(cap, "tier", "")
    main_p = getattr(cap, "main_pos", "")
    sub_p = getattr(cap, "sub_pos", "")
    return f"[{team}](팀장) {c_nick}({real}) / {tier} / {main_p} / {sub_p}"

def fmt_player_as_won(p) -> str:
    """
    낙찰 된 팀원: [팀명] 닉네임(이름) / 티어 / 주 라인 / 부 라인 (낙찰P)
    """
    name = getattr(p, "name", "")
    nick = getattr(p, "nickname", "")
    tier = getattr(p, "tier", "")
    main_p = getattr(p, "main_pos", "")
    sub_p = getattr(p, "sub_pos", "")
    team = getattr(p, "won_team", "") or ""
    price = getattr(p, "won_price", None)
    price_str = f"{price}P" if price is not None else ""
    return f"[{team}] {nick}({name}) / {tier} / {main_p} / {sub_p} ({price_str})"

def fmt_player_as_other(p) -> str:
    """
    그 외 경매자: 닉네임(이름) / 티어 / 주 라인 / 부 라인 (현 상태)
    """
    name = getattr(p, "name", "")
    nick = getattr(p, "nickname", "")
    tier = getattr(p, "tier", "")
    main_p = getattr(p, "main_pos", "")
    sub_p = getattr(p, "sub_pos", "")
    status = getattr(p, "status", "대기")
    return f"{nick}({name}) / {tier} / {main_p} / {sub_p} ({status})"

def find_captain_key_by_teamname(service, team_name: str) -> str | None:
    """
    팀명으로 teams dict의 key(=팀장 닉네임)를 찾는다.
    없으면 하위호환으로 사용자가 팀장 닉을 직접 넣은 경우도 허용.
    """
    target = norm(team_name)
    for c_nick, cap in service.state.captains.items():
        if norm(getattr(cap, "team_name", "")) == target:
            return c_nick
    if team_name in service.state.teams:
        return team_name
    return None
