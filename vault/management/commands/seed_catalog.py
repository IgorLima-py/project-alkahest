# vault/management/commands/seed_catalog.py
import sys
import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from vault.models import Store, GameStoreLink, MasterGame
from vault.services import _process_and_save_game
from vault.utils_igdb import get_igdb_token, CLIENT_ID, BASE_URL

class Command(BaseCommand):
    help = 'Seed em 2 Etapas: IDs Primeiro (Leve), Detalhes Depois (Pesado).'

    def add_arguments(self, parser):
        parser.add_argument('--amount', type=int, default=10)
        parser.add_argument('--offset', type=int, default=0)

    def handle(self, *args, **options):
        amount = options['amount']
        offset = options['offset']
        token = get_igdb_token()
        
        if not token: return

        # 1. Configura Lojas (Steam, PSN, etc)
        active_stores = {}
        for s in [{'slug': 'steam', 'id': 1}, {'slug': 'gog', 'id': 5}, 
                  {'slug': 'epic', 'id': 26}, {'slug': 'xbox', 'id': 11}, 
                  {'slug': 'psn', 'id': 36}]:
            obj, _ = Store.objects.get_or_create(slug=s['slug'], defaults={'igdb_category_id': s['id'], 'name': s['slug'].upper()})
            active_stores[s['id']] = obj

        headers = {'Client-ID': CLIENT_ID, 'Authorization': f'Bearer {token}', 'Accept': 'application/json'}

        # ==============================================================================
        # ETAPA 1: Conseguir apenas os IDs (Operação Ultra Leve)
        # ==============================================================================
        self.stdout.write("--- 1. Obtendo IDs dos Jogos Populares ---")
        
        # Pedimos APENAS o ID. Isso o IGDB consegue ordenar sem travar.
        body_ids = (
            f"fields id; " 
            f"where category = 0 & themes != (42); " # Sem Erotica
            f"sort follows desc; " 
            f"limit {amount}; "
            f"offset {offset};"
        )
        
        resp = requests.post(f"{BASE_URL}/games", headers=headers, data=body_ids)
        
        if resp.status_code != 200:
            self.stdout.write(self.style.ERROR(f"Erro ao pegar IDs: {resp.text}"))
            return
            
        id_list_data = resp.json()
        if not id_list_data:
            self.stdout.write(self.style.ERROR("Nenhum ID retornado. O offset pode estar muito alto."))
            return

        # Transforma em lista simples: [1020, 1942, 333, ...]
        target_ids = [str(item['id']) for item in id_list_data]
        ids_str = ",".join(target_ids)
        
        self.stdout.write(self.style.SUCCESS(f"-> IDs Capturados: {len(target_ids)}"))

        # ==============================================================================
        # ETAPA 2: O Método "Original" (Busca por ID Específico)
        # ==============================================================================
        self.stdout.write("--- 2. Baixando Detalhes (Igual ao seu script original) ---")

        # Agora usamos a query pesada, mas segura porque filtramos por ID
        fields = (
            "name, slug, total_rating_count, category, summary, storyline, "
            "cover.url, screenshots.url, artworks.url, "
            "genres.name, themes.name, first_release_date, "
            "external_games.uid, external_games.category" # <--- O QUE IMPORTA
        )
        
        body_details = f"fields {fields}; where id = ({ids_str}); limit {amount};"
        
        resp_details = requests.post(f"{BASE_URL}/games", headers=headers, data=body_details)
        games_data = resp_details.json()

        # ==============================================================================
        # ETAPA 3: Salvar
        # ==============================================================================
        count_new = 0
        count_links = 0
        
        with transaction.atomic():
            for game in games_data:
                try:
                    # Salva MasterGame
                    master, created = _process_and_save_game(game)
                    if created: count_new += 1
                    
                    # Salva Links
                    if 'external_games' in game:
                        for ext in game['external_games']:
                            cat = ext.get('category')
                            uid = ext.get('uid')
                            
                            if cat in active_stores and uid:
                                _, link_created = GameStoreLink.objects.update_or_create(
                                    master_game=master,
                                    store=active_stores[cat],
                                    external_id=uid
                                )
                                if link_created: count_links += 1
                                
                except Exception as e:
                    print(f"Erro {game.get('name')}: {e}")

        self.stdout.write(self.style.SUCCESS(f"Fim! {count_new} jogos criados, {count_links} links gerados."))
