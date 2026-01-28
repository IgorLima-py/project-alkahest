from django.core.management.base import BaseCommand
from vault.models import MasterGame
from vault.services import fetch_and_update_game # Usa o service robusto que criamos
import time

class Command(BaseCommand):
    help = 'Enriquece metadados (Capa, Generos, etc) de jogos importados incompletos'

    def handle(self, *args, **options):
        # Critério: Jogos sem capa OU com IDs provisórios (acima de 900mi)
        # IDs do IGDB reais geralmente são menores que 200.000 (atualmente)
        targets = MasterGame.objects.filter(igdb_id__gt=900000000) | MasterGame.objects.filter(cover_url__isnull=True)
        
        total = targets.count()
        self.stdout.write(f"Encontrados {total} jogos precisando de enriquecimento...")

        for i, master in enumerate(targets):
            self.stdout.write(f"[{i+1}/{total}] Buscando dados para: {master.title}...")
            
            # Tenta buscar pelo nome no IGDB
            # O service fetch_and_update_game já faz a lógica de search "nome"
            # E retorna um NOVO ou ATUALIZADO MasterGame com ID real
            real_master = fetch_and_update_game(search_name=master.title)
            
            if real_master:
                # OROBOROS: O Problema do Merge
                # O service criou um novo MasterGame com ID real do IGDB (ex: 123).
                # Nós temos o MasterGame provisório (ex: 900000123).
                # Precisamos mover os PlatformGames do provisório para o real e apagar o provisório.
                
                if real_master.id != master.id:
                    self.stdout.write(self.style.SUCCESS(f"   -> MATCH! ID Real: {real_master.igdb_id}. Realizando Merge..."))
                    
                    # Move os filhos (PlatformGames, Tips, Lists)
                    for pg in master.platforms.all():
                        pg.master_game = real_master
                        pg.save()
                    
                    # Apaga o provisório
                    master.delete()
                else:
                    self.stdout.write(self.style.SUCCESS("   -> Dados atualizados no mesmo registro."))
            else:
                self.stdout.write(self.style.WARNING("   -> Não encontrado no IGDB. Mantendo provisório."))
            
            time.sleep(0.3) # Rate limit

        self.stdout.write(self.style.SUCCESS("Enriquecimento concluído!"))