from django.core.management.base import BaseCommand
import requests
import time
from decouple import config
from vault.utils_igdb import get_igdb_token
from vault.services import _process_and_save_game

class Command(BaseCommand):
    help = 'Importa os Top X jogos mais avaliados do IGDB para popular o banco'

    def add_arguments(self, parser):
        parser.add_argument('--amount', type=int, default=100, help='Quantidade de jogos para importar')

    def handle(self, *args, **options):
        amount = options['amount']
        self.stdout.write(f"Iniciando importação de {amount} jogos...")

        token = get_igdb_token()
        client_id = config('TWITCH_CLIENT_ID')
        headers = {'Client-ID': client_id, 'Authorization': f'Bearer {token}'}

        # CAMPOS ATUALIZADOS (Compatível com o novo MasterGame Rico)
        fields = (
            "name, slug, status, category, parent_game, "
            "summary, storyline, first_release_date, "
            "cover.url, screenshots.url, artworks.url, videos.video_id, "
            "involved_companies.company.name, involved_companies.developer, involved_companies.publisher, "
            "game_engines.name, "
            "genres.name, themes.name, game_modes.name, player_perspectives.name, "
            "collection.name, franchises.name, similar_games, dlcs, "
            "language_supports.language.name, language_supports.language_support_type.name, "
            "websites.url, websites.category"
        )
        
        limit = 50 
        offset = 0
        total_processed = 0

        while total_processed < amount:
            current_limit = min(limit, amount - total_processed)
            
            # CORREÇÃO AQUI: 'themes' no plural e adicionado 'id' explicitamente
            body = (
                f"fields id, {fields}; "
                f"where category = (0,8,9,10) & total_rating_count > 50 & themes != (42); " 
                f"sort total_rating_count desc; "
                f"limit {current_limit}; offset {offset};"
            )

            try:
                response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=body)
                data = response.json()
                
                # Tratamento de erro da API (Para não crashar o script se a query falhar)
                if isinstance(data, list) and len(data) > 0 and 'title' in data[0] and 'status' in data[0]:
                     self.stdout.write(self.style.ERROR(f"Erro da API IGDB: {data[0].get('title')} - {data[0].get('detail')}"))
                     break

                if not data:
                    break

                for game_data in data:
                    # Garantia extra de segurança
                    if 'id' in game_data:
                        _process_and_save_game(game_data)
                    else:
                        print(f"PULADO (Dados inválidos): {game_data}")
                
                total_processed += len(data)
                offset += len(data)
                self.stdout.write(self.style.SUCCESS(f"Processados {total_processed}/{amount} jogos..."))
                
                time.sleep(0.3) 

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Erro fatal no batch: {e}"))
                break

        self.stdout.write(self.style.SUCCESS("Importação concluída!"))