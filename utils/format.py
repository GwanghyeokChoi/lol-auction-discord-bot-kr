from typing import Optional, List

def norm_optional(s: Optional[str]) -> Optional[str]:
    if s is None:
        return None
    v = s.strip()
    if v == "" or v.lower() in {"null", "none", "없음"}:
        return None
    return v

def split_semicolon(payload: str, expected_min: int, expected_max: int) -> List[str]:
    parts = [p.strip() for p in payload.split(";")]
    if len(parts) < expected_min:
        raise ValueError("필수 항목이 부족합니다.")
    if len(parts) < expected_max:
        parts += [""] * (expected_max - len(parts))
    return parts[:expected_max]

def fmt_player_line(p) -> str:
    mosts = [p.most1, p.most2, p.most3]
    mosts = [m for m in mosts if m]
    most_str = ", ".join(mosts) if mosts else "-"
    base = (f"**{p.nickname}** ({p.name}) | 티어:{p.tier} | 주:{p.main_pos} 부:{p.sub_pos} | "
            f"모스트:{most_str} | 상태:{p.status}")
    if p.status == "낙찰":
        base += f" | 팀:{p.won_team} | 낙찰:{p.won_price}P"
    return base
