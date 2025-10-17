import asyncio
import csv
import io
import random
import datetime
from typing import Optional
import discord

from models.entities import AuctionState, Player, Captain, Team
from utils.format import fmt_player_line, norm_optional
from components.open_panel import OpenPanelLauncher
import config as CFG

class AuctionService:
    def __init__(self):
        self.state = AuctionState()
        
    def reset_all(self):
        """경매 전체 상태 초기화"""
        self.state = AuctionState()

    def ensure_channel(self, channel_id: int) -> bool:
        if not CFG.ENFORCE_SINGLE_CHANNEL:
            return True
        if self.state.channel_id is None:
            self.state.channel_id = channel_id
        return self.state.channel_id == channel_id

    def add_captain(self, team_name, real_name, nick, tier, main_p, sub_p, m1, m2=None, m3=None, team_limit=None):
        m1 = norm_optional(m1)
        m2 = norm_optional(m2)
        m3 = norm_optional(m3)
        if not (team_name and real_name and nick and tier and main_p and sub_p and m1):
            raise ValueError("필수 항목 누락")
        self.state.captains[nick] = Captain(team_name, real_name, nick, tier, main_p, sub_p, m1, m2, m3)
        self.state.teams[nick] = Team(captain_nick=nick, limit=team_limit or CFG.TEAM_LIMIT)

    def add_player(self, name, nick, tier, main_p, sub_p, m1, m2=None, m3=None):
        m1 = norm_optional(m1)
        m2 = norm_optional(m2)
        m3 = norm_optional(m3)
        if not (name and nick and tier and main_p and sub_p and m1):
            raise ValueError("필수 항목 누락")
        self.state.players[nick] = Player(name, nick, tier, main_p, sub_p, m1, m2, m3)

    def start_auction(self, channel_id: int, total_teams: int, initial_points: int):
        if self.state.started:
            raise RuntimeError("이미 경매 시작")
        if total_teams <= 0 or initial_points <= 0:
            raise ValueError("팀수/포인트 오류")
        if not self.ensure_channel(channel_id):
            raise RuntimeError("다른 채널에서 진행 중")

        self.state.total_teams = total_teams
        self.state.started = True
        self.state.channel_id = channel_id

        for c in self.state.captains.values():
            c.total_pts = initial_points
            c.used_pts = 0
            c.pause_used = 0

        self.state.captain_order = list(self.state.captains.keys())
        random.shuffle(self.state.captain_order)

        self.state.player_order = [p.nickname for p in self.state.players.values() if p.status == "대기"]
        random.shuffle(self.state.player_order)

        self.state.current_player_idx = -1
        self.state.current_captain_idx = 0
        self.state.reset_round()

    async def run_loop(self, ctx):
        PREVIEW_DELAY_SEC = getattr(CFG, "PREVIEW_DELAY_SEC", getattr(CFG, "NEXT_PLAYER_DELAY_SEC", 5))

        def any_team_can_add() -> bool:
            for c_nick in self.state.captains.keys():
                team = self.state.teams.get(c_nick)
                if team and team.can_add():
                    return True
            return False

        async def play_round(round_title: str | None = None):
            if round_title:
                await ctx.send(round_title)

            while self.state.current_player_idx + 1 < len(self.state.player_order):
                self.state.current_player_idx += 1
                p_nick = self.state.player_order[self.state.current_player_idx]
                p = self.state.players.get(p_nick)
                if not p or p.status != "대기":
                    continue

                if not any_team_can_add():
                    p.status = "유찰"
                    await ctx.send(f"모든 팀이 만원이라 **{p.nickname}** 자동 유찰.")
                    continue

                # ── (1) 예고 + 카운트다운 ──
                await self._preview_countdown(ctx, p, PREVIEW_DELAY_SEC)

                # ── (2) 본 경매 시작 선언 & 라운드 초기화 ──
                self.state.reset_round()
                p.status = "진행"
                await ctx.send(
                    f"{fmt_player_line(p)}\n"
                    f"입찰 규칙: 최소 {CFG.BASE_BID}P, {CFG.BID_STEP}P 단위"
                )

                # ── (3) 실제 입찰 루프 (여기서 버튼/텍스트 입력 가능) ──
                await self.bidding_loop(ctx, p)

                # 전략 타임 (모든 팀 최소 1명 영입 시 1회)
                if not self.state.strategy_called and self.state.everyone_has_member():
                    self.state.strategy_called = True
                    await ctx.send(f"📣 모든 팀장에게 팀원이 1명 이상! 전략 타임 {CFG.STRATEGY_TIME_MINUTES//60}분 시작.")
                    await asyncio.sleep(CFG.STRATEGY_TIME_MINUTES)
                    await ctx.send("전략 타임 종료, 경매 재개!")

                # 라운드 간 간격(옵션)
                gap = getattr(CFG, "POST_PLAYER_GAP_SEC", 0)
                if gap > 0:
                    await asyncio.sleep(gap)

        # ── 1라운드 ──
        if self.state.current_player_idx is None:
            self.state.current_player_idx = -1
        if self.state.current_captain_idx is None:
            self.state.current_captain_idx = 0
        await play_round()

        # ── 유찰자 재경매(1회) ──
        failed_players = [pl for pl in self.state.players.values() if pl.status == "유찰"]
        if failed_players and any_team_can_add():
            for pl in failed_players:
                pl.status = "대기"
            self.state.player_order = [pl.nickname for pl in failed_players]
            random.shuffle(self.state.player_order)

            self.state.current_player_idx = -1
            self.state.current_captain_idx = 0
            self.state.reset_round()

            await play_round("🔁 **유찰자 재경매 라운드 시작**")

        await ctx.send("✅ 모든 경매 종료. `!파일 내보내기`로 CSV를 받을 수 있어요.")

    async def bidding_loop(self, ctx, player: Player):
        """
        - captain_user_map에 바인딩된 팀장(user_id)이 있으면 에페메랄 패널(런처→패널)로 입찰/패스/퍼즈
        - 바인딩 없으면 텍스트 명령 폴백
        - ✅ 현재 최고 입찰자에게 다시 턴이 오기 전에 자동 낙찰 처리
        """
        import asyncio, datetime
        from components.open_panel import OpenPanelLauncher
        passed_round = set()

        def get_user_id_for_captain(captain_nick: str) -> int | None:
            for uid, nick in self.state.captain_user_map.items():
                if nick == captain_nick:
                    return uid
            return None

        while True:
            for _ in range(len(self.state.captain_order)):
                c_nick = self.state.captain_order[self.state.current_captain_idx]
                captain = self.state.captains[c_nick]
                team = self.state.teams.get(c_nick)
                if not team:
                    team = Team(captain_nick=c_nick, limit=CFG.TEAM_LIMIT)
                    self.state.teams[c_nick] = team

                # 팀 인원 제한 → 참여 스킵
                if not team.can_add():
                    await ctx.send(f"{self.mention_for_captain(c_nick)} 팀은 인원 제한으로 이번 경매 참여 불가.")
                    self.state.current_captain_idx = (self.state.current_captain_idx + 1) % len(self.state.captain_order)
                    continue

                # 퍼즈 만료 체크
                if self.state.paused_until:
                    now = datetime.datetime.utcnow()
                    if now < self.state.paused_until:
                        await asyncio.sleep(1)
                        continue
                    self.state.paused_until = None
                    self.state.pause_owner = None
                    await ctx.send("⏱️ 퍼즈 만료, 경매 재개.")

                # 🔸(중요) 현재 최고 입찰자에게 턴이 다시 오면 자동 낙찰
                if (
                    self.state.current_bidder  # 누군가 이미 입찰했고
                    and self.state.current_bidder == c_nick  # 그가 지금 차례이며
                    and len(passed_round) == len(self.state.captain_order) - 1  # 나를 제외한 모두가 패스/타임아웃
                ):
                    win = self.state.current_bidder
                    cap = self.state.captains[win]
                    t = self.state.teams[win]
                    cap.used_pts += self.state.current_bid
                    t.members.append(player.nickname)
                    player.status = "낙찰"
                    player.won_team = cap.team_name
                    player.won_price = self.state.current_bid
                    await ctx.send(f"🎉 **{player.nickname}** 낙찰! 팀 **{cap.team_name}**, 가격 **{self.state.current_bid}P**")
                    return

                # ── 한 턴 입력 수집 ──
                action, amount = None, None
                author_id = get_user_id_for_captain(c_nick)

                if author_id is not None:
                    # 에페메랄 패널 런처 사용
                    loop = asyncio.get_running_loop()
                    result_future = loop.create_future()
                    launcher = OpenPanelLauncher(
                        author_id=author_id,
                        service=self,
                        captain_key=c_nick,
                        min_bid=CFG.BASE_BID,
                        step=CFG.BID_STEP,
                        max_bid=captain.remain_pts,
                        current_top=self.state.current_bid,
                        timeout_sec=CFG.TURN_BID_TIMEOUT_SEC,
                        pause_max_sec=CFG.PAUSE_MAX_DURATION_SEC,
                        pause_max_count=CFG.PAUSE_MAX_PER_CAPTAIN,
                        result_future=result_future,
                    )
                    prompt_msg = await ctx.send(
                        f"배팅 차례: {self.mention_for_captain(c_nick)} (잔여 {captain.remain_pts}) — 아래 버튼으로 ‘본인만’ 에페메랄 패널을 열 수 있습니다.",
                        view=launcher
                    )
                    try:
                        action, amount = await asyncio.wait_for(result_future, timeout=CFG.TURN_BID_TIMEOUT_SEC)
                    except asyncio.TimeoutError:
                        action, amount = "pass", None
                        await ctx.send(f"⏱️ {self.mention_for_captain(c_nick)} 시간 초과로 자동 패스.")
                    # 런처 비활성
                    try:
                        for ch in launcher.children:
                            ch.disabled = True
                        await prompt_msg.edit(view=launcher)
                    except Exception:
                        pass

                else:
                    # 텍스트 폴백
                    await ctx.send(
                        f"배팅 차례: {self.mention_for_captain(c_nick)} (잔여 {captain.remain_pts}) — "
                        f"`!입찰 <포인트>` / `!패스` / `!퍼즈` ({CFG.TURN_BID_TIMEOUT_SEC}초)\n"
                        "※ `!팀장 연결 <팀장닉네임>`으로 바인딩하면 버튼(에페메랄) UI를 사용할 수 있어요."
                    )

                    def is_turn_message(m: discord.Message) -> bool:
                        if m.channel.id != ctx.channel.id:
                            return False
                        mapped = self.state.captain_user_map.get(m.author.id)
                        if mapped:
                            return mapped == c_nick
                        name = (m.author.display_name or "").strip()
                        uname = (m.author.name or "").strip()
                        return name == c_nick or uname == c_nick

                    try:
                        msg = await ctx.bot.wait_for("message", timeout=CFG.TURN_BID_TIMEOUT_SEC, check=is_turn_message)
                        content = msg.content.strip()
                        if content.startswith("!입찰"):
                            parts = content.split()
                            if len(parts) >= 2 and parts[1].lstrip("-").isdigit():
                                amount = int(parts[1]); action = "bid"
                            else:
                                await ctx.send("예) `!입찰 100`"); action = None
                        elif content.startswith("!패스"):
                            action = "pass"
                        elif content.startswith("!퍼즈 종료"):
                            if self.state.pause_owner == c_nick:
                                self.state.paused_until = None
                                self.state.pause_owner = None
                                await ctx.send("▶️ 퍼즈 해제!")
                            else:
                                await ctx.send("퍼즈를 건 팀장만 해제할 수 있습니다.")
                            action = None
                        elif content.startswith("!퍼즈"):
                            if self.state.pause_owner and self.state.pause_owner != c_nick:
                                await ctx.send("이미 누군가 퍼즈 중입니다.")
                            elif captain.pause_used >= CFG.PAUSE_MAX_PER_CAPTAIN:
                                await ctx.send("퍼즈 횟수를 모두 사용했습니다.")
                            else:
                                captain.pause_used += 1
                                self.state.pause_owner = c_nick
                                self.state.paused_until = datetime.datetime.utcnow() + datetime.timedelta(seconds=CFG.PAUSE_MAX_DURATION_SEC)
                                await ctx.send(f"⏸️ {self.mention_for_captain(c_nick)} 퍼즈! 최대 {CFG.PAUSE_MAX_DURATION_SEC//60}분. `!퍼즈 종료`로 조기 해제.")
                            action = None
                        else:
                            action = None
                    except asyncio.TimeoutError:
                        action, amount = "pass", None
                        await ctx.send(f"⏱️ {self.mention_for_captain(c_nick)} 시간 초과로 자동 패스.")

                # ── 입력 결과 반영 ──
                if action == "bid":
                    bid = int(amount or 0)
                    if bid < CFG.BASE_BID or bid % CFG.BID_STEP != 0:
                        await ctx.send(f"입찰은 최소 {CFG.BASE_BID}P, {CFG.BID_STEP}P 단위입니다.")
                    elif bid <= self.state.current_bid:
                        await ctx.send(f"현재 최고 {self.state.current_bid}P 입니다.")
                    elif bid > captain.remain_pts:
                        await ctx.send(f"보유 포인트({captain.remain_pts})를 초과했어요.")
                    else:
                        self.state.current_bid = bid
                        self.state.current_bidder = c_nick
                        passed_round = set()
                        await ctx.send(f"🟢 {self.mention_for_captain(c_nick)} **{bid}P** 입찰!")

                elif action == "pass":
                    passed_round.add(c_nick)
                    await ctx.send(f"🔵 {self.mention_for_captain(c_nick)} 패스.")

                # 다음 팀장 차례
                self.state.current_captain_idx = (self.state.current_captain_idx + 1) % len(self.state.captain_order)

                # ✅ 일반 정산: 모두 패스 + 최고 입찰자 없음 → 유찰
                if len(passed_round) == len(self.state.captain_order) and not self.state.current_bidder:
                    player.status = "유찰"
                    await ctx.send(f"⚪ **{player.nickname}** 유찰.")
                    return

                # ✅ 일반 정산: 누군가 입찰했고, 그 이후 모두 패스 → 낙찰
                if len(passed_round) == len(self.state.captain_order) and self.state.current_bidder:
                    win = self.state.current_bidder
                    cap = self.state.captains[win]
                    t = self.state.teams[win]
                    cap.used_pts += self.state.current_bid
                    t.members.append(player.nickname)
                    player.status = "낙찰"
                    player.won_team = cap.team_name
                    player.won_price = self.state.current_bid
                    await ctx.send(f"🎉 **{player.nickname}** 낙찰! 팀 **{cap.team_name}**, 가격 **{self.state.current_bid}P**")
                    return

    def export_csv_bytes(self) -> bytes:
        out = io.StringIO()
        writer = csv.writer(out)
        writer.writerow(["팀명", "이름", "닉네임", "주 라인", "부 라인", "모스트", "포인트"])

        for c_nick, team in self.state.teams.items():
            cap = self.state.captains.get(c_nick)
            team_name = getattr(cap, "team_name", "") if cap else ""

            for mn in team.members:  # mn = 팀원 닉네임(문자열)
                p = self.state.players.get(mn)
                if not p:
                    # 혹시 일관성 깨졌을 때도 한 줄은 쓰고 넘어가도록
                    writer.writerow([team_name, "", mn, "", "", "", ""])
                    continue

                # 필드명 혼용 안전 처리
                real_name = getattr(p, "name", "")
                nickname = getattr(p, "nickname", mn)

                main_pos = getattr(p, "main_p", getattr(p, "main_pos", ""))
                sub_pos  = getattr(p, "sub_p",  getattr(p, "sub_pos",  ""))

                # 모스트 필드 다양한 이름 대응
                most_vals = [
                    getattr(p, "m1", None) or getattr(p, "most1", None),
                    getattr(p, "m2", None) or getattr(p, "most2", None),
                    getattr(p, "m3", None) or getattr(p, "most3", None),
                ]
                # None/빈값 제거 후 ", "로 연결
                most_joined = ", ".join([m for m in most_vals if m])

                price = getattr(p, "won_price", "") or ""

                writer.writerow([team_name, real_name, nickname, main_pos, sub_pos, most_joined, price])

        return out.getvalue().encode("utf-8-sig")
        
    def bind_captain_user(self, user_id: int, captain_nick: str):
        if captain_nick not in self.state.captains:
            raise ValueError("해당 팀장 닉네임이 없습니다.")
        self.state.captain_user_map[user_id] = captain_nick

    def get_captain_user_id(self, captain_nick: str) -> int | None:
        # AuctionState.captain_user_map: Dict[user_id, captain_nick]
        for uid, nick in self.state.captain_user_map.items():
            if nick == captain_nick:
                return uid
        return None

    async def _preview_countdown(self, ctx, player, seconds: int):
        """다음 경매자 예고 + 카운트다운 메시지 1개를 계속 수정"""
        base = (
            "📢 **다음 경매자 예고**\n"
            f"{fmt_player_line(player)}\n"
        )
        # 처음 한 번 전송
        msg = await ctx.send(base + f"⏳ {seconds}초 뒤 시작합니다! 준비해 주세요.")
        # 1초마다 편집
        for s in range(seconds - 1, -1, -1):
            await asyncio.sleep(1)
            try:
                await msg.edit(content=base + (f"⏳ {s}초 뒤 시작합니다! 준비해 주세요." if s > 0 else "▶️ **경매 시작!**"))
            except Exception:
                # 메시지 삭제/권한 변경 등으로 edit 실패 시 새로 보내고 계속
                msg = await ctx.send(base + (f"⏳ {s}초 뒤 시작합니다! 준비해 주세요." if s > 0 else "▶️ **경매 시작!**"))
        return msg  # 마지막 메시지 객체 반환

    # AuctionService 내부
    def mention_for_captain(self, c_nick: str) -> str:
        for uid, nick in self.state.captain_user_map.items():
            if nick == c_nick:
                return f"<@{uid}>"
        return c_nick