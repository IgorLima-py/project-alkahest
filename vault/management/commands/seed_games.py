# vault/management/commands/seed_games.py

from django.core.management.base import BaseCommand
import requests
import time
from decouple import config
from django.db import transaction

# --- ADIÇÃO 1: NOSSOS NOVOS MODELS ---
from vault.models import MasterGame, Store, GameStoreLink 
from vault.utils_igdb import get_igdb_token
from vault.services import _process_and_save_game

class Command(BaseCommand):
    help = 'Importa e enriquece os Top X jogos do IGDB, incluindo links de lojas.'

    def add_arguments(self, parser):
        parser.add_argument('--amount', type=int, default=100, help='Quantidade de jogos para importar')

    @transaction.atomic # Adicionado para segurança das operações no banco
    def handle(self, *args, **options):
        amount = options['amount']
        self.stdout.write(f"Iniciando importação de {amount} jogos...")

        token = get_igdb_token()
        client_id = config('TWITCH_CLIENT_ID')
        headers = {'Client-ID': client_id, 'Authorization': f'Bearer {token}'}

        # SUA LISTA DE CAMPOS ORIGINAL + O CAMPO ESSENCIAL 'external_games'
        fields = (
            "name, slug, status, category, parent_game, "
            "summary, storyline, first_release_date, "
            "cover.url, screenshots.url, artworks.url, videos.video_id, "
            "involved_companies.company.name, involved_companies.developer, involved_companies.publisher, "
            "game_engines.name, "
            "genres.name, themes.name, game_modes.name, player_perspectives.name, "
            "collection.name, franchises.name, similar_games, dlcs, "
            "language_supports.language.name, language_supports.language_support_type.name, "
            "websites.url, websites.category, "
            "external_games.category, external_games.uid" # O CAMPO ADICIONADO
        )
        
        # Pega as lojas que já cadastramos no banco
        supported_stores = {s.igdb_category_id: s for s in Store.objects.filter(igdb_category_id__isnull=False)}

        limit = 50 
        offset = 0
        total_processed = 0

        while total_processed < amount:
            current_limit = min(limit, amount - total_processed)
            
            body = (
                f"fields id, {fields}; "
                f"where category = (0,8,9,10) & total_rating_count > 50 & themes != (42); " 
                f"sort total_rating_count desc; "
                f"limit {current_limit}; offset {offset};"
            )

            try:
                response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=body)
                response.raise_for_status() # Lança erro se a resposta não for 200 OK
                data = response.json()
                
                if not data:
                    self.stdout.write(self.style.WARNING("Não há mais jogos que correspondam aos critérios."))
                    break

                for game_data in data:
                    if 'id' in game_data:
                        # 1. SALVA O MASTERGAME (Sua função original)
                        # Assumimos que _process_and_save_game retorna o objeto MasterGame
                        master_game = _process_and_save_game(game_data)
                        
                        # --- ADIÇÃO 2: O BLOCO QUE SALVA OS LINKS ---
                        if master_game: # Só prossiga se o jogo foi salvo corretamente
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
                        # --- FIM DA ADIÇÃO ---
                    else:
                        print(f"PULADO (Dados inválidos): {game_data}")
                
                total_processed += len(data)
                offset += len(data)
                self.stdout.write(self.style.SUCCESS(f"Processados {total_processed}/{amount} jogos..."))
                
                time.sleep(0.3) 

            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f"Erro na requisição: {e}"))
                # Para depuração, vamos ver o que a API respondeu
                if e.response is not None:
                    self.stdout.write(self.style.ERROR(f"Resposta da API: {e.response.text}"))
                break

        self.stdout.write(self.style.SUCCESS("Importação concluída!"))