# components/unpause_view.py
import datetime
import discord

class UnpauseView(discord.ui.View):
    def __init__(self, *, author_id: int, service, captain_key: str, timeout: int | None = 300):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.service = service
        self.captain_key = captain_key

    async def _unpause(self, interaction: discord.Interaction):
        state = self.service.state
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("이 버튼은 해당 팀장만 사용할 수 있습니다.", ephemeral=True)

        if state.pause_owner != self.captain_key:
            return await interaction.response.send_message("현재 퍼즈 소유자가 아닙니다.", ephemeral=True)

        state.paused_until = None
        state.pause_owner = None

        try:
            await interaction.channel.send("▶️ 퍼즈 해제!")
        except Exception:
            pass
        await interaction.response.edit_message(content="퍼즈가 해제되었습니다.", view=None)

    @discord.ui.button(label="퍼즈 종료", style=discord.ButtonStyle.success)
    async def do_unpause(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._unpause(interaction)
