from django.core.management.base import BaseCommand
from vault.models import MasterGame
from vault.services import fetch_and_update_game # Usa o service robusto que criamos
import time

class Command(BaseCommand):
    help = 'Enriquece jogos usando SteamID se disponível, ou Nome como fallback'

    def handle(self, *args, **options):
        # Pega jogos provisórios ou sem capa
        targets = MasterGame.objects.filter(igdb_id__gt=900000000) | MasterGame.objects.filter(cover_url__isnull=True)
        total = targets.count()
        
        self.stdout.write(f"Otimizando {total} jogos...")

        for i, master in enumerate(targets):
            # Tenta achar um ID da Steam ligado a este MasterGame
            steam_pg = master.platforms.filter(platform__slug='steam').first()
            steam_id = steam_pg.external_id if steam_pg else None
            
            self.stdout.write(f"[{i+1}/{total}] {master.title} (SteamID: {steam_id})...")
            
            # Chama o service passando Steam ID (Prioridade) e Nome (Fallback)
            real_master = fetch_and_update_game(search_name=master.title, steam_id=steam_id)
            
            if real_master:
                if real_master.id != master.id:
                    self.stdout.write(self.style.SUCCESS(f"   -> MATCH! ID {real_master.igdb_id}. Mesclando..."))
                    for pg in master.platforms.all():
                        pg.master_game = real_master
                        pg.save()
                    master.delete()
                else:
                    self.stdout.write(self.style.SUCCESS("   -> Atualizado."))
            else:
                self.stdout.write(self.style.WARNING("   -> Não encontrado."))
            
            time.sleep(0.3)

        self.stdout.write(self.style.SUCCESS("Enriquecimento concluído!"))