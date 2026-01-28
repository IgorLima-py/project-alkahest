from django.core.management.base import BaseCommand
from ...models import MasterGame
from ...services import fetch_and_update_game
import time

class Command(BaseCommand):
    help = 'Força a atualização de todos os jogos já cadastrados no banco via IGDB'

    def handle(self, *args, **options):
        games = MasterGame.objects.all()
        total = games.count()
        self.stdout.write(f"Encontrados {total} jogos para atualizar...")

        for i, game in enumerate(games):
            self.stdout.write(f"[{i+1}/{total}] Atualizando: {game.title} (ID: {game.igdb_id})...")
            
            # Chama o service passando o ID que já temos.
            # Isso vai baixar capa nova, developer, engine, etc.
            fetch_and_update_game(igdb_id=game.igdb_id)
            
            time.sleep(0.3) # Respeita o rate limit do IGDB

        self.stdout.write(self.style.SUCCESS("Biblioteca atualizada com sucesso!"))