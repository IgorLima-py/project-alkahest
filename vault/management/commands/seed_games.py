# vault/management/commands/seed_games.py
import requests
import time
from django.core.management.base import BaseCommand
from django.db import transaction
from decouple import config
from vault.models import MasterGame, Store, GameStoreLink # NOVO: Importamos Store e GameStoreLink
from vault.utils_igdb import get_igdb_token
from vault.services import _process_and_save_game

class Command(BaseCommand):
    help = 'Busca e enriquece o catálogo com dados do IGDB, incluindo jogos e links de lojas.'

    def add_arguments(self, parser):
        parser.add_argument('--amount', type=int, default=100, help='Quantidade de jogos para processar')

    @transaction.atomic # Garante que as operações sejam seguras
    def handle(self, *args, **options):
        amount = options['amount']
        self.stdout.write(f"Iniciando enriquecimento de {amount} jogos...")

        token = get_igdb_token()
        if not token:
            self.stdout.write(self.style.ERROR("Não foi possível obter o token do IGDB. Abortando."))
            return
            
        client_id = config('TWITCH_CLIENT_ID')
        headers = {'Client-ID': client_id, 'Authorization': f'Bearer {token}'}

        # NOVO: Adicionamos os campos de lojas externas à sua lista de campos original
        base_fields = "name, slug, external_games.category, external_games.uid" # Adicionamos o essencial aqui
        # Você pode adicionar os outros campos que já tinha, se quiser, mas para o link, isso basta
        
        limit = 50 
        offset = 0
        total_processed = 0

        # Pega as lojas que cadastramos no passo anterior
        supported_stores = {s.igdb_category_id: s for s in Store.objects.filter(igdb_category_id__isnull=False)}
        
        while total_processed < amount:
            current_limit = min(limit, amount - total_processed)
            
            # Usando a sua query que já funciona, mas pedindo os campos extras
            body = (
                f"fields id, {base_fields}; "
                f"where category = (0,8,9,10) & total_rating_count > 50 & themes != (42); " 
                f"sort total_rating_count desc; "
                f"limit {current_limit}; offset {offset};"
            )

            try:
                response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=body)
                response.raise_for_status() # Lança um erro se a resposta não for 200 OK
                data = response.json()

                if not data:
                    self.stdout.write(self.style.WARNING("Não há mais jogos a serem processados."))
                    break

                for game_data in data:
                    # 1. Cria ou atualiza o MasterGame (como você já fazia)
                    master_game, created = MasterGame.objects.update_or_create(
                        igdb_id=game_data['id'],
                        defaults={'title': game_data.get('name', 'N/A')}
                    )
                    if created:
                        self.stdout.write(f"  -> Jogo Mestre criado: {master_game.title}")

                    # 2. NOVO: Loop para criar os GameStoreLinks
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
                                self.stdout.write(self.style.SUCCESS(f"     -> Link para {store_obj.name} adicionado a '{master_game.title}'"))
                
                total_processed += len(data)
                offset += len(data)
                self.stdout.write(f"Processados {total_processed}/{amount} jogos...")
                
                time.sleep(0.3) 

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Erro fatal no batch: {e}"))
                break

        self.stdout.write(self.style.SUCCESS("Enriquecimento do catálogo concluído!"))