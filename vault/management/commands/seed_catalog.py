# vault/management/commands/seed_catalog.py
import sys
from django.core.management.base import BaseCommand
from django.db import transaction
from vault.models import Store, GameStoreLink
from vault.services import _process_and_save_game
from vault.utils_igdb import igdb_api_request, IGDBError

class Command(BaseCommand):
    help = 'Popula o catálogo buscando os jogos mais populares do IGDB dinamicamente.'

    # Mapeamento Oficial IGDB (external_games.category) -> Slug da sua Loja
    IGDB_CATEGORY_MAP = {
        1: 'steam',
        5: 'gog',
        26: 'epic-games',
        # PSN/Xbox via external_games são instáveis, mantemos PC por enquanto
    }

    def add_arguments(self, parser):
        parser.add_argument('--amount', type=int, default=50, help='Quantidade de jogos para importar')
        parser.add_argument('--offset', type=int, default=0, help='Pular os primeiros N jogos (útil para continuar de onde parou)')

    def _ensure_stores_exist(self):
        """Garante que as lojas existam no DB antes de linkar"""
        stores_data = [
            {'slug': 'steam', 'name': 'Steam', 'igdb_id': 1},
            {'slug': 'gog', 'name': 'GOG.com', 'igdb_id': 5},
            {'slug': 'epic-games', 'name': 'Epic Games Store', 'igdb_id': 26},
            {'slug': 'xbox', 'name': 'Microsoft Store', 'igdb_id': 11},
            {'slug': 'playstation', 'name': 'PlayStation Store', 'igdb_id': 36},
        ]
        created_count = 0
        for s in stores_data:
            obj, created = Store.objects.get_or_create(
                slug=s['slug'],
                defaults={'name': s['name'], 'igdb_category_id': s['igdb_id']}
            )
            if created: created_count += 1
        
        if created_count > 0:
            self.stdout.write(self.style.SUCCESS(f"Lojas inicializadas: {created_count} criadas."))

    def handle(self, *args, **options):
        total_amount = options['amount']
        current_offset = options['offset']
        batch_size = 50 # IGDB aceita até 500, mas 50 é mais seguro para processar sem estourar memória
        
        self._ensure_stores_exist()
        
        # Carrega lojas em memória para acesso rápido
        active_stores = {
            s.igdb_category_id: s 
            for s in Store.objects.filter(igdb_category_id__in=self.IGDB_CATEGORY_MAP.keys())
        }

        self.stdout.write(f"--- INICIANDO SEED: Top {total_amount} Jogos (Offset: {current_offset}) ---")

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
            "external_games.category, external_games.uid" # CRUCIAL para preços
        )

        processed_count = 0

        while processed_count < total_amount:
            # Calcula o tamanho do batch atual (pode ser menor na última iteração)
            fetch_limit = min(batch_size, total_amount - processed_count)
            
            # Query IGDB: Ordena por seguidores (proxy de popularidade)
            # category = 0 garante que pegamos apenas "Main Games" (evita DLCs soltas por enquanto)
            body = (
                f"fields {fields}; "
                f"where category = 0 & themes != (42); " # themes!=42 remove Erotica
                f"sort follows desc; " 
                f"limit {fetch_limit}; "
                f"offset {current_offset};"
            )

            try:
                self.stdout.write(f"Baixando batch: {fetch_limit} jogos (Offset: {current_offset})...")
                games_data = igdb_api_request('games', body)
                
                if not games_data:
                    self.stdout.write(self.style.WARNING("IGDB não retornou mais dados. Fim da lista."))
                    break

                # Processamento Atômico por Jogo (Se um falhar, não quebra o script todo)
                for game_data in games_data:
                    try:
                        with transaction.atomic():
                            # 1. Salva o MasterGame (Usa sua função do services.py)
                            master_game, created = _process_and_save_game(game_data)
                            
                            # 2. Cria Links de Loja (Apenas para as lojas que mapeamos)
                            links_created = 0
                            external_games = game_data.get('external_games', [])
                            if external_games:
                                for ext in external_games:
                                    cat_id = ext.get('category')
                                    uid = ext.get('uid')
                                    
                                    # Se a categoria do IGDB bater com uma das nossas lojas mapeadas
                                    if cat_id in active_stores and uid:
                                        store_obj = active_stores[cat_id]
                                        
                                        # Cria o Link
                                        _, link_created = GameStoreLink.objects.update_or_create(
                                            master_game=master_game,
                                            store=store_obj,
                                            defaults={'external_id': uid} # UID da Steam/Epic/GOG
                                        )
                                        if link_created: links_created += 1

                            # Feedback visual discreto
                            status_char = "+" if created else "."
                            if links_created > 0: status_char += f"[{links_created}L]"
                            self.stdout.write(status_char, ending="")
                            sys.stdout.flush()

                    except Exception as e:
                        self.stdout.write(self.style.ERROR(f"\nErro no jogo {game_data.get('name')}: {e}"))

                # Atualiza contadores
                processed_count += len(games_data)
                current_offset += len(games_data)
                self.stdout.write("") # Quebra de linha após os pontinhos

            except IGDBError as e:
                self.stdout.write(self.style.ERROR(f"Erro Crítico na API: {e}"))
                break

        self.stdout.write(self.style.SUCCESS(f"\n--- CONCLUÍDO! {processed_count} jogos processados. ---"))
