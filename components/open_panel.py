# components/open_panel.py
import asyncio
import discord
from components.bid_panel import BidPanel

class OpenPanelLauncher(discord.ui.View):
    """
    공개 메시지의 '내 입찰 패널 열기' 버튼:
    - 클릭한 유저가 author_id와 같으면 에페메랄 BidPanel을 attach_to()로 띄움
    - 결과는 result_future로 bidding_loop에 전달
    """
    def __init__(
        self,
        *,
        author_id: int,
        service,
        captain_key: str,
        min_bid: int,
        step: int,
        max_bid: int,
        current_top: int,
        timeout_sec: int,
        pause_max_sec: int,
        pause_max_count: int,
        result_future: asyncio.Future,
    ):
        super().__init__(timeout=timeout_sec)
        self.author_id = author_id
        self.service = service
        self.captain_key = captain_key
        self.min_bid = min_bid
        self.step = step
        self.max_bid = max_bid
        self.current_top = current_top
        self.timeout_sec = timeout_sec
        self.pause_max_sec = pause_max_sec
        self.pause_max_count = pause_max_count
        self.result_future = result_future

    @discord.ui.button(label="내 입찰 패널 열기", style=discord.ButtonStyle.primary)
    async def open_panel(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 권한 없는 사람은 에페메랄 경고
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("현재 차례인 팀장만 열 수 있습니다.", ephemeral=True)

        # 해당 사용자에게만 에페메랄 입찰 패널 표시
        panel = BidPanel(
            author_id=self.author_id,
            min_bid=self.min_bid,
            step=self.step,
            max_bid=self.max_bid,
            current_top=self.current_top,
            timeout_sec=self.timeout_sec,
            service=self.service,
            captain_key=self.captain_key,
            pause_max_sec=self.pause_max_sec,
            pause_max_count=self.pause_max_count,
            result_future=self.result_future,
        )
        # ❗ attach_to는 내부에서 response.send_message 1회만 호출 → 중복 응답 방지
        await panel.attach_to(interaction)
