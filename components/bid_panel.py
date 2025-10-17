# components/bid_panel.py
import datetime
import asyncio
import discord
from components.unpause_view import UnpauseView

class BidPanel(discord.ui.View):
    """
    - author_id만 상호작용 가능(interaction_check)
    - 증감 버튼을 누를 때마다 '현재 입찰 금액' + '현재 최고가 대비 차이'가 갱신
    - 퍼즈 시 퍼즈 종료 버튼은 에페메랄로 표시
    - 인터랙션 응답은 중복 호출되지 않도록 edit_message/response 호출을 엄격히 분리
    """
    def __init__(
        self,
        *,
        author_id: int,
        min_bid: int,
        step: int,
        max_bid: int,
        current_top: int,
        timeout_sec: int,
        service,
        captain_key: str,
        pause_max_sec: int,
        pause_max_count: int,
        result_future: asyncio.Future,
    ):
        super().__init__(timeout=timeout_sec)
        self.author_id = author_id
        self.min_bid = min_bid
        self.step = step
        self.max_bid = max_bid
        self.current_top = current_top or 0
        self._amount = max(min_bid, (self.current_top + step) if self.current_top else min_bid)

        self.service = service
        self.captain_key = captain_key
        self.pause_max_sec = pause_max_sec
        self.pause_max_count = pause_max_count
        self._result_future = result_future

        # 에페메랄 패널의 "원본 메시지"를 편집하려면 original_response를 써야 함
        self._has_initial_responded = False

    # ─────────────────────────────────────────────
    async def on_timeout(self):
        if not self._result_future.done():
            self._result_future.set_result(("timeout", None))

        # 뷰 비활성화 시도 (ephemeral이라도 edit_original_response로 가능)
        try:
            if self._has_initial_responded:
                msg = await self._get_original()
                for c in self.children:
                    c.disabled = True
                await msg.edit(content=self.get_content(), view=self)
        except Exception:
            pass

    # ─────────────────────────────────────────────
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        """버튼 권한 확인"""
        if interaction.user and interaction.user.id == self.author_id:
            return True
        # 권한 없는 유저에겐 에페메랄 경고
        if not interaction.response.is_done():
            await interaction.response.send_message("현재 차례인 팀장만 조작할 수 있습니다.", ephemeral=True)
        else:
            await interaction.followup.send("현재 차례인 팀장만 조작할 수 있습니다.", ephemeral=True)
        return False

    def _set_result(self, action: str, amount: int | None):
        if not self._result_future.done():
            self._result_future.set_result((action, amount))

    # ✅ 패널 상단 표시: 현재 최고가, 내 금액, 차이
    def get_content(self) -> str:
        diff = self._amount - (self.current_top or 0)
        sign = "+" if diff >= 0 else "-"
        diff_abs = abs(diff)
        return (
            f"🏷️ **현재 최고가:** {self.current_top}P\n"
            f"💰 **내 금액:** {self._amount}P ({sign}{diff_abs}P)\n"
            f"최대 {self.max_bid}P까지, 버튼으로 조정하세요."
        )

    async def attach_to(self, interaction: discord.Interaction):
        """
        최초 호출 시: 반드시 이 메서드로 에페메랄 패널을 띄워야 함.
        (response.send_message 1회, 이후는 edit_original_response 사용)
        """
        await interaction.response.send_message(self.get_content(), view=self, ephemeral=True)
        self._has_initial_responded = True

    async def _get_original(self) -> discord.Message:
        # 에페메랄도 original_response로 핸들 가능
        return await self._interaction.followup.fetch_message(self._message_id)  # (미사용 패턴) → 아래 방식 사용

    async def _edit_panel(self, interaction: discord.Interaction):
        """
        버튼 클릭 시 현재 패널을 업데이트.
        - 최초 응답 이후에는 edit_original_response를 사용해야 안전.
        """
        if not interaction.response.is_done():
            # 같은 인터랙션에서 아직 응답을 안했다면 이 인터랙션으로 바로 편집
            await interaction.response.edit_message(content=self.get_content(), view=self)
        else:
            # 이미 응답된 인터랙션이라면 original을 편집
            await interaction.edit_original_response(content=self.get_content(), view=self)

    # ─────────────────────── 증감 버튼 ───────────────────────
    async def _adjust_bid(self, interaction: discord.Interaction, delta: int):
        new = self._amount + delta
        if new > self.max_bid:
            return await interaction.response.send_message("보유 포인트를 초과합니다.", ephemeral=True)
        if new < self.min_bid:
            return await interaction.response.send_message("최소 입찰 금액보다 낮게 설정할 수 없습니다.", ephemeral=True)
        self._amount = new
        await self._edit_panel(interaction)

    @discord.ui.button(label="+10", style=discord.ButtonStyle.secondary, row=0)
    async def inc10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._adjust_bid(interaction, self.step)

    @discord.ui.button(label="+50", style=discord.ButtonStyle.secondary, row=0)
    async def inc50(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._adjust_bid(interaction, self.step * 5)

    @discord.ui.button(label="+100", style=discord.ButtonStyle.secondary, row=0)
    async def inc100(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._adjust_bid(interaction, self.step * 10)

    @discord.ui.button(label="-10", style=discord.ButtonStyle.secondary, row=1)
    async def dec10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._adjust_bid(interaction, -self.step)

    @discord.ui.button(label="-50", style=discord.ButtonStyle.secondary, row=1)
    async def dec50(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._adjust_bid(interaction, -self.step * 5)

    @discord.ui.button(label="-100", style=discord.ButtonStyle.secondary, row=1)
    async def dec100(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._adjust_bid(interaction, -self.step * 10)

    # ─────────────────────── 확정 / 패스 / 퍼즈 ───────────────────────
    @discord.ui.button(label="입찰", style=discord.ButtonStyle.success, row=2)
    async def do_confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._set_result("bid", self._amount)
        if not interaction.response.is_done():
            await interaction.response.edit_message(content=f"✅ 입찰 확정: **{self._amount}P**", view=None)
        else:
            await interaction.edit_original_response(content=f"✅ 입찰 확정: **{self._amount}P**", view=None)

    @discord.ui.button(label="패스", style=discord.ButtonStyle.primary, row=2)
    async def do_pass(self, interaction: discord.Interaction, button: discord.ui.Button):
        self._set_result("pass", None)
        if not interaction.response.is_done():
            await interaction.response.edit_message(content="🔵 패스 선택", view=None)
        else:
            await interaction.edit_original_response(content="🔵 패스 선택", view=None)

    @discord.ui.button(label="퍼즈", style=discord.ButtonStyle.danger, row=2)
    async def do_pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        state = self.service.state

        if state.pause_owner and state.pause_owner != self.captain_key:
            return await interaction.response.send_message("이미 누군가 퍼즈 중입니다.", ephemeral=True)

        cap = self.service.state.captains.get(self.captain_key)
        if not cap:
            return await interaction.response.send_message("팀장 정보를 찾을 수 없습니다.", ephemeral=True)

        if cap.pause_used >= self.pause_max_count:
            return await interaction.response.send_message("퍼즈 횟수를 모두 사용했습니다.", ephemeral=True)

        # 퍼즈 시작
        cap.pause_used += 1
        state.pause_owner = self.captain_key
        state.paused_until = datetime.datetime.utcnow() + datetime.timedelta(seconds=self.pause_max_sec)
        await interaction.channel.send(f"⏸️ {self.captain_key} 퍼즈! 최대 {self.pause_max_sec//60}분. `!퍼즈 종료`로 조기 해제.")

        # 퍼즈 종료 버튼 (에페메랄)
        view = UnpauseView(author_id=self.author_id, service=self.service, captain_key=self.captain_key)
        if not interaction.response.is_done():
            await interaction.response.send_message(
                "퍼즈 중입니다. 필요 시 아래 버튼으로 즉시 해제할 수 있어요.",
                view=view,
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                "퍼즈 중입니다. 필요 시 아래 버튼으로 즉시 해제할 수 있어요.",
                view=view,
                ephemeral=True,
            )
