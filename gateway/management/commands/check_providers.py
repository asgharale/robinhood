import asyncio

from django.core.management.base import BaseCommand

from gateway import router


class Command(BaseCommand):
    help = "Send a tiny request to every configured provider key and report which work."

    def handle(self, *args, **options):
        asyncio.run(self.run_all())

    async def run_all(self):
        if not router.GROUPS:
            self.stdout.write("No provider keys configured (check .env)")
        for group in router.GROUPS:
            for p in group:
                try:
                    await router._call(p, [{"role": "user", "content": "Say OK"}], 5)
                    self.stdout.write(f"OK    {p.name}  {p.model}")
                except router.ProviderError as e:
                    self.stdout.write(f"FAIL  {p.name}  {p.model}: {e}")
        await router.get_client().aclose()