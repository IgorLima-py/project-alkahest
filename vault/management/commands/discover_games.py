import time
from django.core.management.base import BaseCommand
from vault.models import MasterGame, Store, GameStoreLink
from vault.utils_igdb import IGDB  # Assumindo que seu utilitário tem uma classe IGDB

class Command(BaseCommand):
    help = 'Busca jogos populares no IGDB e popula as tabelas MasterGame e GameStoreLink.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='Quantos jogos buscar por vez.')
        parser.add_argument('--offset', type=int, default=0, help='De qual posição começar a busca.')

    def handle(self, *args, **options):
        limit = options['limit']
        offset = options['offset']

        self.stdout.write(self.style.WARNING(f"🚀 Iniciando descoberta de jogos no IGDB (Limit={limit}, Offset={offset})"))
        
        igdb_client = IGDB() # Inicializa seu cliente IGDB
        
        # Pega as lojas que cadastramos e cria um mapa para fácil acesso
        # Ex: {1: <Store: Steam>, 36: <Store: PlayStation Store>}
        supported_stores = {s.igdb_category_id: s for s in Store.objects.filter(igdb_category_id__isnull=False)}
        
        # Adapte esta chamada para como seu utils_igdb.py funciona
        games_data = igdb_client.get_top_games_with_stores(limit=limit, offset=offset)

        if not games_data:
            self.stdout.write(self.style.ERROR("❌ Nenhum jogo encontrado no IGDB com os critérios."))
            return

        created_games = 0
        created_links = 0

        for game_data in games_data:
            # 1. Cria ou Atualiza o MasterGame
            master_game, created = MasterGame.objects.update_or_create(
                igdb_id=game_data['id'],
                defaults={
                    'title': game_data.get('name', 'N/A'),
                    'cover_url': game_data.get('cover', {}).get('url', '').replace('t_thumb', 't_cover_big'),
                    'summary': game_data.get('summary', ''),
                    # Adicione outros campos do seu MasterGame que o IGDB retorna
                }
            )
            if created:
                created_games += 1
                self.stdout.write(f"  -> Jogo Mestre criado: {master_game.title}")

            # 2. Varre os links de lojas externas
            external_games = game_data.get('external_games', [])
            if not external_games:
                continue

            for external_link in external_games:
                store_category = external_link.get('category')
                
                # Verifica se é uma loja que a gente suporta
                if store_category in supported_stores:
                    store_obj = supported_stores[store_category]
                    
                    # Cria ou Atualiza o GameStoreLink
                    _, link_created = GameStoreLink.objects.get_or_create(
                        store=store_obj,
                        external_id=external_link['uid'],
                        defaults={'master_game': master_game}
                    )
                    
                    if link_created:
                        created_links += 1
                        self.stdout.write(f"     -> Link criado para {store_obj.name}")
        
        self.stdout.write(self.style.SUCCESS(f"🏁 Descoberta finalizada!"))
        self.stdout.write(f"   Jogos Mestres criados: {created_games}")
        self.stdout.write(f"   Links de Loja criados: {created_links}")