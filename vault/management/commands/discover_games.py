# vault/management/commands/discover_games.py
from django.core.management.base import BaseCommand
from django.db import transaction
from vault.models import MasterGame, Store, GameStoreLink
from vault import utils_igdb # Importa o módulo inteiro

class Command(BaseCommand):
    help = 'Busca jogos populares no IGDB e popula as tabelas MasterGame e GameStoreLink.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100, help='Quantos jogos buscar por vez.')
        parser.add_argument('--offset', type=int, default=0, help='De qual posição começar a busca.')

    @transaction.atomic # Garante que todas as operações no banco sejam seguras
    def handle(self, *args, **options):
        limit = options['limit']
        offset = options['offset']

        self.stdout.write(self.style.WARNING(f"🚀 Iniciando descoberta de jogos no IGDB (Limit={limit}, Offset={offset})"))
        
        # Pega as lojas que cadastramos e cria um mapa para fácil acesso
        supported_stores = {s.igdb_category_id: s for s in Store.objects.filter(igdb_category_id__isnull=False)}
        
        # CHAMA A NOVA FUNÇÃO CORRETAMENTE
        games_data = utils_igdb.get_top_games_with_stores(limit=limit, offset=offset)

        if not games_data:
            self.stdout.write(self.style.ERROR("❌ Nenhum jogo encontrado no IGDB. Verifique as credenciais ou a API."))
            return

        created_games = 0
        created_links = 0
        
        # Usamos um set para evitar prints repetidos para o mesmo jogo
        processed_games = set()

        for game_data in games_data:
            # 1. Cria ou Atualiza o MasterGame
            master_game, created = MasterGame.objects.update_or_create(
                igdb_id=game_data['id'],
                defaults={'title': game_data.get('name', 'N/A')}
            )
            if created and master_game.id not in processed_games:
                created_games += 1
                self.stdout.write(f"  -> Jogo Mestre criado: {master_game.title}")
                processed_games.add(master_game.id)

            # 2. Varre os links de lojas externas
            for external_link in game_data.get('external_games', []):
                store_category = external_link.get('category')
                if store_category in supported_stores:
                    store_obj = supported_stores[store_category]
                    
                    _, link_created = GameStoreLink.objects.get_or_create(
                        store=store_obj,
                        external_id=external_link['uid'],
                        defaults={'master_game': master_game}
                    )
                    
                    if link_created:
                        created_links += 1
                        self.stdout.write(f"     -> Link para {store_obj.name} adicionado a '{master_game.title}'")
        
        self.stdout.write(self.style.SUCCESS(f"🏁 Descoberta finalizada!"))
        self.stdout.write(f"   Jogos Mestres criados/atualizados: {len(games_data)}")
        self.stdout.write(f"   Novos Links de Loja criados: {created_links}")