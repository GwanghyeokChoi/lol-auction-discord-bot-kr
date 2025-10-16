# components/bid_panel.py
import discord
from discord.ui import View, Button
import asyncio

class BidPanel(View):
    def __init__(self, *, author_id: int, min_bid: int, step: int, max_bid: int, current_top: int, timeout_sec: int = 5):
        super().__init__(timeout=timeout_sec)
        self.author_id = author_id
        self.min_bid = min_bid
        self.step = step
        self.max_bid = max_bid
        self.current_top = current_top
        self.value = None  # ('bid', amount) | ('pass', None) | ('pause', None) | ('timeout', None)
        self._event = asyncio.Event()
        # 내부 상태
        self._amount = max(self.min_bid, ((self.current_top // self.step) + 1) * self.step)

    # ——— 권한 필터: 내 차례인 사람만 조작 ———
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user and interaction.user.id == self.author_id:
            return True
        await interaction.response.send_message("현재 차례인 팀장만 조작할 수 있습니다.", ephemeral=True)
        return False

    # ——— 버튼 콜백들 ———
    async def _adjust_bid(self, interaction: discord.Interaction, delta: int):
        """입찰 금액 증감 처리 (delta: + 또는 - 정수)"""
        new = self._amount + delta
        # 최소~최대 범위 체크
        if new > self.max_bid:
            await interaction.response.send_message("보유 포인트를 초과합니다.", ephemeral=True)
            return
        if new < self.min_bid:
            await interaction.response.send_message("최소 입찰 금액보다 낮게 설정할 수 없습니다.", ephemeral=True)
            return
        self._amount = new
        await interaction.response.edit_message(view=self._render())

    @discord.ui.button(label="-100", style=discord.ButtonStyle.secondary, row=0)
    async def dec100(self, interaction: discord.Interaction, button: Button):
        await self._adjust_bid(interaction, -self.step * 10)

    @discord.ui.button(label="-50", style=discord.ButtonStyle.secondary, row=0)
    async def dec50(self, interaction: discord.Interaction, button: Button):
        await self._adjust_bid(interaction, -self.step * 5)

    @discord.ui.button(label="-10", style=discord.ButtonStyle.secondary, row=0)
    async def dec10(self, interaction: discord.Interaction, button: Button):
        await self._adjust_bid(interaction, -self.step)

    @discord.ui.button(label="+10", style=discord.ButtonStyle.secondary, row=1)
    async def inc10(self, interaction: discord.Interaction, button: Button):
        await self._adjust_bid(interaction, self.step)

    @discord.ui.button(label="+50", style=discord.ButtonStyle.secondary, row=1)
    async def inc50(self, interaction: discord.Interaction, button: Button):
        await self._adjust_bid(interaction, self.step * 5)

    @discord.ui.button(label="+100", style=discord.ButtonStyle.secondary, row=1)
    async def inc100(self, interaction: discord.Interaction, button: Button):
        await self._adjust_bid(interaction, self.step * 10)

    @discord.ui.button(label="입찰 확정", style=discord.ButtonStyle.success, row=2)
    async def confirm(self, interaction: discord.Interaction, button: Button):
        if self._amount <= self.current_top or self._amount < self.min_bid or self._amount % self.step != 0:
            await interaction.response.send_message("유효한 입찰 금액이 아닙니다.", ephemeral=True)
            return
        self.value = ("bid", self._amount)
        self._event.set()
        await interaction.response.edit_message(view=self._disable_all())

    @discord.ui.button(label="패스", style=discord.ButtonStyle.primary, row=2)
    async def do_pass(self, interaction: discord.Interaction, button: Button):
        self.value = ("pass", None)
        self._event.set()
        await interaction.response.edit_message(view=self._disable_all())

    @discord.ui.button(label="퍼즈", style=discord.ButtonStyle.danger, row=2)
    async def do_pause(self, interaction: discord.Interaction, button: Button):
        self.value = ("pause", None)
        self._event.set()
        await interaction.response.edit_message(view=self._disable_all())

    # ——— 유틸 ———
    def _render(self) -> "BidPanel":
        # 버튼 라벨에 현재 제시가 노출되도록
        for child in self.children:
            if isinstance(child, Button) and child.label and "입찰 확정" in child.label:
                child.label = f"입찰 확정 ({self._amount}P)"
        return self

    def _disable_all(self) -> "BidPanel":
        for child in self.children:
            child.disabled = True
        return self

    async def wait_result(self) -> tuple[str, int | None]:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=self.timeout)
        except asyncio.TimeoutError:
            self.value = ("timeout", None)
        return self.value or ("timeout", None)
