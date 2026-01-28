from django.core.management.base import BaseCommand
import requests
import time
from decouple import config
from ...utils_igdb import get_igdb_token
from ...services import _process_and_save_game # Usamos a interna pra processar o lote

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

        # Query batch otimizada: Pega jogos populares com todos os campos necessários
        # Ordenado por rating_count para pegar os mais populares/famosos
        fields = (
            "name, slug, cover.url, first_release_date, summary, category, parent_game, "
            "genres.name, involved_companies.company.name, involved_companies.developer, "
            "involved_companies.publisher, game_engines.name, "
            "websites.url, websites.category"
        )
        
        limit = 50 # Batch size do IGDB
        offset = 0
        total_processed = 0

        while total_processed < amount:
            current_limit = min(limit, amount - total_processed)
            body = (
                f"fields {fields}; "
                f"where category = (0,8,9,10) & total_rating_count > 50 & theme != (42); " # Apenas Main, Remake, Remaster + Filtro anti-porn (42)
                f"sort total_rating_count desc; "
                f"limit {current_limit}; offset {offset};"
            )

            try:
                response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=body)
                data = response.json()
                
                if not data:
                    break

                for game_data in data:
                    _process_and_save_game(game_data)
                
                total_processed += len(data)
                offset += len(data)
                self.stdout.write(self.style.SUCCESS(f"Processados {total_processed}/{amount} jogos..."))
                
                time.sleep(0.3) # Rate limit preventivo (4 req/s max)

            except Exception as e:
                self.stdout.write(self.style.ERROR(f"Erro no batch: {e}"))
                break

        self.stdout.write(self.style.SUCCESS("Importação concluída!"))