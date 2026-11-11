from .cog import BossCog


async def setup(bot):
    await bot.add_cog(BossCog(bot))
