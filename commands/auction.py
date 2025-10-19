import io
import csv
import asyncio
import discord
from discord.ext import commands

from utils.format import split_semicolon, fmt_player_line
from services.auction_service import AuctionService
import config as CFG

from models.view_format import (
    norm,
    fmt_captain_line,
    fmt_player_as_won,
    fmt_player_as_other,
    find_captain_key_by_teamname,
)

# 서비스는 모듈 전역에서 하나만 사용
service = AuctionService()

def same_channel_guard(ctx: commands.Context) -> bool:
    """경매는 한 채널에서만 진행 — 다른 채널이면 False"""
    return service.ensure_channel(ctx.channel.id)

def _author_matches_nick(self, ctx: commands.Context, target_nick: str) -> bool:
    """현재 메시지 발신자가 target_nick 팀장인지 판별 (매핑 우선 → 표시이름/계정명 대안)"""
    # 1) user_id → nick 매핑 우선
    mapped = self.service.state.captain_user_map.get(ctx.author.id)
    if mapped:
        return mapped == (target_nick or "").strip()
    # 2) 표시이름/계정명 매칭 (하위 호환)
    name = (ctx.author.display_name or "").strip()
    uname = (ctx.author.name or "").strip()
    target = (target_nick or "").strip()
    return name == target or uname == target

class AuctionCog(commands.Cog, name="Auction"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.service = service  # 필요 시 교체/모킹 가능

    # Cog 전체에 적용할 체크(모든 커맨드 공통)
    async def cog_check(self, ctx: commands.Context) -> bool:
        return same_channel_guard(ctx)

    # ───────────────────────── 도움말 ─────────────────────────
    @commands.command(name="도움말")
    async def help_cmd(self, ctx: commands.Context, *args):
        """
        !도움말            → 전체 명령어 요약
        !도움말 <토픽>    → 상세 도움말 (경매, 팀장, 경매자, 입찰, 조회, 파일)
        """
        base_bid = CFG.BASE_BID
        bid_step = CFG.BID_STEP
        turn_sec = CFG.TURN_BID_TIMEOUT_SEC
        pause_cnt = CFG.PAUSE_MAX_PER_CAPTAIN
        pause_sec = CFG.PAUSE_MAX_DURATION_SEC
        strategy_min = CFG.STRATEGY_TIME_MINUTES

        COMMANDS = {
            "도움말": (
                "!도움말 [토픽]",
                "전체 명령어 요약 또는 특정 토픽의 상세 도움말을 보여줍니다."
            ),
            "팀장 등록": (
                "!팀장 등록 팀명;이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]",
                "팀장을 등록합니다. 모스트2/3는 비워도 됩니다."
            ),
            "팀장 연결": (
                "!팀장 연결 <팀장닉네임>",
                "내 디스코드 계정을 팀장 닉네임에 바인딩합니다. 버튼 UI 입찰이 활성화됩니다."
            ),
            "경매자 등록": (
                "!경매자 등록 (CSV 첨부) 또는 !경매자 등록 이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]",
                "경매자를 등록합니다. CSV 첨부 시 명령만 입력하면 됩니다."
            ),
            "경매 시작": (
                "!경매 시작 <팀수> <팀장초기포인트>",
                f"경매를 시작합니다. 최소입찰 {base_bid}P, 단위 {bid_step}P, 턴 제한 {turn_sec}초."
            ),
            "입찰": (
                f"본인 차례(버튼 UI)에서 금액을 확정합니다. 최소 {base_bid}P, {bid_step}P 단위, 잔여 포인트 이내."
            ),
            "패스": (
                "이번 라운드 입찰을 건너뜁니다. 모두 패스 + 최고입찰자 없음이면 유찰."
            ),
            "관심 없음": (
                "현재 진행 중인 경매에서 참여를 포기합니다.",
                "‘패스’는 다른 팀장이 입찰하면 이후 다시 참여할 수 있지만, "
                "‘관심 없음’을 선택하면 해당 경매에는 끝까지 참여할 수 없습니다."
            ),
            "퍼즈": (
                f"경매 일시정지. 팀장당 {pause_cnt}회, 1회 최대 {pause_sec//60}분.",
                "퍼즈는 퍼즈를 건 팀장만 해제할 수 있습니다."
            ),
            "조회 참가자": (
                "!조회 참가자 <이름/닉네임>",
                "경매자 또는 팀장 정보를 단일 명령으로 조회합니다. (이름, 닉네임, 현재상태, 낙찰가 포함)"
            ),
            "조회 팀원": (
                "!조회 팀원 <팀명>",
                "해당 팀의 팀원과 낙찰가를 조회합니다."
            ),
            "조회 유찰자": (
                "!조회 유찰자",
                "유찰된 경매자 목록을 조회합니다."
            ),
            "조회 포인트": (
                "!조회 포인트 <팀명>",
                "팀의 전체/사용/잔여 포인트를 조회합니다."
            ),
            "조회 경매순서": (
                "!조회 경매순서 또는 !조회 경매 순서",
                "경매 예정 순서와 상태(대기/진행/낙찰/유찰)를 조회합니다. (띄어쓰기 허용)"
            ),
            "유찰": (
                "진행 중 경매자를 강제 유찰 처리(관리용). 모든 라운드 종료 후 유찰자 재경매 1회 진행."
            ),
            "파일 내보내기": (
                "!파일 내보내기",
                "경매 결과를 CSV로 다운로드합니다."
            ),
        }

        TOPICS = {
            "경매": ("경매 시작/진행", [
                "① 팀장 등록: `!팀장 등록 팀명;이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]` (팀장 전원 등록)",
                "② 경매자 등록: `!경매자 등록` + CSV 첨부  또는  `!경매자 등록 이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]`",
                "③ (선택) 팀장-계정 바인딩: `!팀장 연결 <팀장닉네임>` — 내 차례에 **버튼 UI**로 입찰/패스/퍼즈 가능",
                "④ 경매 시작: `!경매 시작 <팀수> <초기포인트>`  예) `!경매 시작 3 1000`",
                "",
                f"입찰: 최소 {base_bid}P, {bid_step}P 단위, 턴당 {turn_sec}초",
                "`패스` — 이번 라운드 건너뛰기",
                "`관심 없음` — 이번 경매 건너뛰기, 패스는 재입찰이 가능하지만 관심 없음은 불가.",
                f"`퍼즈` / `퍼즈 종료` — 팀장당 {pause_cnt}회, 1회 최대 {pause_sec//60}분",
                f"전략 타임 — 모든 팀장에게 1명 이상 영입되면 {strategy_min}분 1회",
                "",
                "⚙️ 경매 리셋/종료: `!경매 리셋`  (진행 중 상태를 초기화하고 재시작할 때 사용)",
            ]),
            "팀장": ("팀장/바인딩", [
                "`!팀장 등록 팀명;이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]`",
                "`!팀장 연결 <팀장닉네임>` — 내 디스코드 계정을 팀장 닉으로 바인딩",
                "바인딩 후 내 차례에 **버튼 UI**가 표시되어 금액 증감/입찰/패스/퍼즈를 버튼으로 선택할 수 있습니다.",
                "팀장 연결을 하지 않은 경우, 경매 참여가 불가능합니다. 참고 부탁드립니다.",
            ]),
            "경매자": ("경매자 등록", [
                "`!경매자 등록` + CSV 첨부 (권장)",
                "`!경매자 등록 이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]`",
                "모스트2/3 비워도 됩니다(자동 무시).",
            ]),
            "입찰": ("입찰 규칙", [
                f"최소 {base_bid}P, {bid_step}P 단위",
                "현재 최고가 초과만 유효",
                "본인 잔여 포인트 이내",
                f"차례당 {turn_sec}초 내 입력",
            ]),
            "조회": ("조회 명령 모음", [
                "📊 통합 명령어 `!조회` 사용법:",
                "  • `!조회 참가자 <이름/닉네임>` — 경매자 또는 팀장 정보 조회 (이름, 닉네임, 현재상태, 낙찰가)",
                "  • `!조회 팀원 <팀명>` — 해당 팀의 팀원과 낙찰가 확인",
                "  • `!조회 유찰자` — 유찰된 경매자 목록 조회",
                "  • `!조회 포인트 <팀명>` — 팀의 전체/사용/잔여 포인트 확인",
                "  • `!조회 경매순서` 또는 `!조회 경매 순서` — 경매 예정 순서 및 상태 확인",
                "",
                "👉 예시:",
                "  `!조회 참가자 홍길동`",
                "  `!조회 참가자 기네스버거#KR1`",
                "  `!조회 팀원 1팀`",
                "  `!조회 유찰자`",
                "  `!조회 포인트 2팀`",
                "  `!조회 경매순서`",
                ]),
            "파일": ("결과 파일", [
                "`!파일 내보내기` — 낙찰 결과 CSV 다운로드",
            ]),
        }

        # 특정 토픽 상세
        if args:
            topic_key = args[0].replace(" ", "")
            for key, (title, lines) in TOPICS.items():
                if key in topic_key:
                    body = "\n".join(f"- {line}" for line in lines)
                    return await ctx.send(f"**[{title}]**\n{body}")
            for name, (usage, desc) in COMMANDS.items():
                if name.replace(" ", "") in topic_key:
                    return await ctx.send(f"**{name}**\n사용법: `{usage}`\n설명: {desc}")
            return await ctx.send("해당 토픽이 없습니다. `!도움말`로 전체 목록을 확인하세요.")

        # 전체 목록
        header = (
            "📖 **명령어 전체 목록**\n"
            "필요시 `!도움말 <토픽>`으로 더 자세한 설명을 볼 수 있어요.\n"
            "예: `!도움말 경매`, `!도움말 팀장`, `!도움말 조회`"
        )
        lines = []
        for n, val in COMMANDS.items():
            # val은 (usage, desc) 2-튜플이어야 하지만, 실수 대비 방어
            if isinstance(val, (list, tuple)) and len(val) >= 2:
                u, d = val[0], val[1]
            elif isinstance(val, (list, tuple)) and len(val) == 1:
                u, d = val[0], ""
            else:
                u, d = str(val), ""
            lines.append(f"- **{n}** — `{u}`\n  · {d}")
        await ctx.send(f"{header}\n\n" + "\n".join(lines))

    # ───────────────────────── 등록/입력 명령 ─────────────────────────
    @commands.command(name="팀장")
    async def captain_cmd(self, ctx: commands.Context, *raw_args):
        """
        !팀장 등록 팀명;이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]
        !팀장 연결 <팀장닉네임>
        """
        if not raw_args:
            return await ctx.send(
                "사용법:\n"
                "• `!팀장 등록 팀명;이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]`\n"
                "• `!팀장 연결 <팀장닉네임>` — 내 디스코드 계정을 팀장 닉에 바인딩(버튼 UI 사용)"
            )

        sub = raw_args[0]

        # ───────── 연결 (바인딩) ─────────
        if sub in ("연결", "bind"):
            captain_nick = " ".join(raw_args[1:]).strip() if len(raw_args) > 1 else None
            if not captain_nick:
                return await ctx.send("사용법: `!팀장 연결 <팀장닉네임>`")
            try:
                self.service.bind_captain_user(ctx.author.id, captain_nick)
            except ValueError as e:
                return await ctx.send(str(e))
            return await ctx.send(
                f"이제 <@{ctx.author.id}> 님은 팀장 **{captain_nick}** 으로 인식됩니다. "
                "본인 차례에 버튼 UI가 표시됩니다."
            )

        # ───────── 등록 ─────────
        if sub != "등록":
            return await ctx.send(
                "사용법:\n"
                "• `!팀장 등록 팀명;이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]`\n"
                "• `!팀장 연결 <팀장닉네임>`"
            )

        payload = " ".join(raw_args[1:]).strip()
        try:
            parts = split_semicolon(payload, expected_min=7, expected_max=9)
            team_name, real_name, nick, tier, main_p, sub_p, m1, m2, m3 = parts
            self.service.add_captain(team_name, real_name, nick, tier, main_p, sub_p, m1, m2, m3)
        except Exception:
            return await ctx.send("형식을 확인해 주세요. 세미콜론(;) 기준 항목 수/순서를 맞춰주세요.")
        await ctx.send(f"팀장 등록 완료: **{team_name}** / {real_name} {nick}")

    @commands.command(name="경매자")
    async def player_cmd(self, ctx: commands.Context, *raw_args):
        # ── 조회 분기 ──
        if raw_args and raw_args[0] in ("조회", "정보"):
            nick = raw_args[1] if len(raw_args) > 1 else None
            if nick:
                p = self.service.state.players.get(nick)
                if not p:
                    return await ctx.send("해당 닉네임이 없습니다.")
                return await ctx.send(fmt_player_line(p))
            desc = "\n".join(fmt_player_line(p) for p in self.service.state.players.values()) or "등록된 경매자가 없습니다."
            return await ctx.send(desc[:1900])

        # ── 등록 분기 (기존 로직) ──
        if not raw_args or raw_args[0] != "등록":
            return await ctx.send("사용법: `!경매자 등록` (CSV 첨부)  /  `!경매자 등록 이름;닉;티어;주;부;모스트1[;모스트2][;모스트3]`  /  `!경매자 조회 [닉]`")

        # CSV 첨부 우선
        if ctx.message.attachments:
            count = 0
            for att in ctx.message.attachments:
                if att.filename.lower().endswith(".csv"):
                    data = await att.read()
                    text = data.decode("utf-8-sig")
                    reader = csv.reader(io.StringIO(text))
                    for row in reader:
                        if not row or row[0].strip().startswith("#"):
                            continue
                        if len(row) < 6:
                            continue
                        name, nick, tier, main_p, sub_p, m1 = [c.strip() for c in row[:6]]
                        m2 = row[6].strip() if len(row) > 6 else None
                        m3 = row[7].strip() if len(row) > 7 else None
                        try:
                            self.service.add_player(name, nick, tier, main_p, sub_p, m1, m2, m3)
                            count += 1
                        except Exception:
                            continue
            return await ctx.send(f"CSV에서 경매자 {count}명 등록 완료.")

        # 수동 입력
        payload = " ".join(raw_args[1:]).strip()
        try:
            parts = split_semicolon(payload, expected_min=6, expected_max=8)
            name, nick, tier, main_p, sub_p, m1, maybe_m2, maybe_m3 = (parts + ["", ""])[:8]
            self.service.add_player(name, nick, tier, main_p, sub_p, m1, maybe_m2, maybe_m3)
        except Exception:
            return await ctx.send("형식을 확인해 주세요. 세미콜론(;) 기준 항목 수/순서를 맞춰주세요.")
        await ctx.send(f"경매자 등록 완료: {nick}")

    # ───────────────────────── 경매 제어 ─────────────────────────
    @commands.command(name="경매")
    async def auction_cmd(self, ctx: commands.Context, sub: str = None, *args):
        # 리셋/종료 지원
        if sub in ("리셋", "종료", "reset", "stop", "end"):
            self.service.reset_all()
            return await ctx.send("🧹 경매 상태를 초기화했습니다. 이제 `!경매 시작 <팀수> <초기포인트>`로 다시 시작하세요.")

        if sub != "시작":
            return await ctx.send("사용법: `!경매 시작 <팀수> <팀장초기포인트>`  또는  `!경매 리셋`")

        # !경매 시작 <팀수> <초기포인트>
        try:
            total_teams_int = int(args[0])
            initial_points_int = int(args[1])
        except (IndexError, ValueError, TypeError):
            return await ctx.send("팀수/포인트는 숫자여야 합니다. 예) `!경매 시작 3 1000`")

        try:
            self.service.start_auction(ctx.channel.id, total_teams_int, initial_points_int)
        except RuntimeError as e:
            # 여기서 "이미 경매 시작"이 나올 수 있음 → 리셋 안내
            return await ctx.send(f"{str(e)}\n필요하면 `!경매 리셋` 후 다시 시작하세요.")
        except Exception:
            return await ctx.send("팀수/포인트를 확인하세요.")

        await ctx.send(f"팀장 배팅 순서: {', '.join(self.service.state.captain_order) if self.service.state.captain_order else '없음'}")
        await ctx.send(f"경매자 수 {len(self.service.state.player_order)}명. 5초 후 시작합니다...")
        await asyncio.sleep(5)
        await self.service.run_loop(ctx)

    # ───────────────────────── 조회 그룹 ─────────────────────────
    @commands.group(name="조회", invoke_without_command=True)
    async def query_group(self, ctx: commands.Context, *args):
        """
        사용법:
        • !조회 팀원 <팀명>
        • !조회 유찰자
        • !조회 포인트 <팀명>
        • !조회 경매순서   (또는 '!조회 경매 순서')
        """
        # '경매 순서' 처럼 띄어쓰기해도 동작하게 라우팅
        tokens = [a.strip() for a in args if a and a.strip()]
        if len(tokens) == 2 and tokens[0] in ("경매", "auction") and tokens[1] in ("순서", "order"):
            return await ctx.invoke(self.query_order)  # 아래 subcommand 호출

        # 도움말
        return await ctx.send(
            "사용법:\n"
            "• `!조회 팀원 <팀명>`\n"
            "• `!조회 유찰자`\n"
            "• `!조회 포인트 <팀명>`\n"
            "• `!조회 경매순서`  (또는 `!조회 경매 순서`)"
        )

    @query_group.command(name="팀원")
    async def query_team_sub(self, ctx: commands.Context, *, team_name: str | None = None):
        if not team_name:
            return await ctx.send("사용법: `!조회 팀원 <팀명>`")

        captain_key = find_captain_key_by_teamname(self.service, team_name)
        if captain_key is None:
            return await ctx.send("해당 팀명을 찾지 못했습니다. 팀명이 정확한지 확인해 주세요.")

        cap = self.service.state.captains.get(captain_key)
        team = self.service.state.teams.get(captain_key)
        if not cap or not team:
            return await ctx.send("팀 정보를 찾지 못했습니다.")

        lines = [fmt_captain_line(captain_key, cap)]

        # 팀에 영입된 멤버(= 낙찰자만) 출력
        if not team.members:
            lines.append("낙찰 된 팀원: (없음)")
        else:
            for mn in team.members:
                p = self.service.state.players.get(mn)
                if p and getattr(p, "status", "") == "낙찰" and getattr(p, "won_team", "") == getattr(cap, "team_name", ""):
                    lines.append(fmt_player_as_won(p))

        text = "\n".join(lines)
        await ctx.send(text[:1900] if text else "결과가 없습니다.")

    @query_group.command(name="유찰자", aliases=["failed", "fail"])
    async def query_failed_sub(self, ctx: commands.Context):
        """
        !조회 유찰자
        포맷: 그 외 경매자: 닉네임(이름) / 티어 / 주 라인 / 부 라인 (현 상태)
        """
        failed = [p for p in self.service.state.players.values() if getattr(p, "status", "") == "유찰"]
        if not failed:
            return await ctx.send("유찰자가 없습니다.")

        from models.view_format import fmt_player_as_other
        lines = [fmt_player_as_other(p) for p in failed]
        text = "\n".join(lines)
        await ctx.send(text[:1900])

    @query_group.command(name="포인트")
    async def query_point_sub(self, ctx: commands.Context, *, team_name: str | None = None):
        if not team_name:
            return await ctx.send("사용법: `!조회 포인트 <팀명>`")
        for c in self.service.state.captains.values():
            if c.team_name == team_name:
                return await ctx.send(f"{team_name} — 전체:{c.total_pts} / 사용:{c.used_pts} / 잔여:{c.remain_pts}")
        await ctx.send("해당 팀명이 없습니다.")

    @query_group.command(name="경매순서", aliases=["경매-순서", "경매_순서"])
    async def query_order(self, ctx: commands.Context):
        po = self.service.state.player_order
        if not po:
            return await ctx.send("경매 순서가 없습니다.")

        lines: list[str] = []
        for nick in po:
            p = self.service.state.players.get(nick)
            if not p:
                continue
            if getattr(p, "status", "") == "낙찰":
                lines.append(fmt_player_as_won(p))
            else:
                lines.append(fmt_player_as_other(p))

        text = "\n".join(lines)
        await ctx.send(text[:1900] if text else "경매 순서가 없습니다.")

        
    @query_group.command(name="참가자", aliases=["participant", "사람"])
    async def query_participant_sub(self, ctx: commands.Context, *, key: str | None = None):
        if not key:
            return await ctx.send("사용법: `!조회 참가자 <이름 또는 닉네임>`")

        q = norm(key)

        # 1) 경매자 탐색
        exact_p, exact_p_by_name = None, None
        partial_p = []
        for p in self.service.state.players.values():
            nick_l = norm(getattr(p, "nickname", ""))
            name_l = norm(getattr(p, "name", ""))
            if nick_l == q:
                exact_p = p
                break
            if exact_p_by_name is None and name_l == q:
                exact_p_by_name = p
            if q in nick_l or q in name_l:
                partial_p.append(p)

        # 2) 팀장 탐색
        exact_c, exact_c_by_name = None, None  # (c_nick, cap)
        partial_c = []
        for c_nick, c in self.service.state.captains.items():
            real_l = norm(getattr(c, "real_name", ""))
            team_l = norm(getattr(c, "team_name", ""))
            cap_nick_l = norm(getattr(c, "nickname", ""))  # 모델에 있을 수도
            key_nick_l = norm(c_nick)
            if key_nick_l == q or cap_nick_l == q:
                exact_c = (c_nick, c)
                break
            if exact_c_by_name is None and real_l == q:
                exact_c_by_name = (c_nick, c)
            if any(q in s for s in (real_l, team_l, cap_nick_l, key_nick_l)):
                partial_c.append((c_nick, c))

        lines: list[str] = []

        # 1순위: 닉 완전일치
        if exact_p:
            if getattr(exact_p, "status", "") == "낙찰":
                lines.append(fmt_player_as_won(exact_p))
            else:
                lines.append(fmt_player_as_other(exact_p))
        if exact_c:
            lines.append(fmt_captain_line(exact_c[0], exact_c[1]))

        # 2순위: 이름 완전일치
        if not lines and exact_p_by_name:
            if getattr(exact_p_by_name, "status", "") == "낙찰":
                lines.append(fmt_player_as_won(exact_p_by_name))
            else:
                lines.append(fmt_player_as_other(exact_p_by_name))
        if not lines and exact_c_by_name:
            lines.append(fmt_captain_line(exact_c_by_name[0], exact_c_by_name[1]))

        # 3순위: 부분일치 후보(최대 5개씩)
        if not lines:
            if partial_p:
                for p in partial_p[:5]:
                    if getattr(p, "status", "") == "낙찰":
                        lines.append(fmt_player_as_won(p))
                    else:
                        lines.append(fmt_player_as_other(p))
            if partial_c:
                for cn, c in partial_c[:5]:
                    lines.append(fmt_captain_line(cn, c))

        if not lines:
            return await ctx.send("해당 이름/닉네임의 참가자를 찾지 못했습니다.")

        text = "\n".join(lines)
        await ctx.send(text[:1900] if text else "결과가 없습니다.")


    # ───────────────────────── 결과 내보내기 ─────────────────────────
    @commands.command(name="파일")
    async def export_cmd(self, ctx: commands.Context, sub: str = None):
        if sub != "내보내기":
            return await ctx.send("사용법: `!파일 내보내기`")
        data = self.service.export_csv_bytes()
        await ctx.send(file=discord.File(io.BytesIO(data), filename="auction_result.csv"))

# 확장 로드용 엔트리
async def setup(bot: commands.Bot):
    await bot.add_cog(AuctionCog(bot))
