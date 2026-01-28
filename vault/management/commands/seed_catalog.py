import time
from django.core.management.base import BaseCommand
from django.db import transaction
from vault.models import MasterGame, Store, GameStoreLink
from vault.services import _process_and_save_game
from vault.utils_igdb import igdb_api_request

class Command(BaseCommand):
    help = 'Popula o catálogo de jogos (MasterGame) e cria os vínculos com lojas (GameStoreLink).'

    # Mapeamento: ID da Categoria no IGDB -> Slug da Loja no nosso sistema
    # Fonte: Documentação IGDB External Games
    IGDB_STORE_MAP = {
        1: {'slug': 'steam', 'name': 'Steam'},
        5: {'slug': 'gog', 'name': 'GOG.com'},
        26: {'slug': 'epic-games', 'name': 'Epic Games Store'},
        11: {'slug': 'xbox', 'name': 'Microsoft Store (Xbox)'},
        36: {'slug': 'playstation', 'name': 'PlayStation Store'},
        # Nuuvem não tem ID oficial no IGDB usually, mas deixamos aqui caso apareça
    }

    def add_arguments(self, parser):
        parser.add_argument('--amount', type=int, default=10, help='Quantidade de jogos para processar')
        parser.add_argument('--offset', type=int, default=0, help='Pular os primeiros N jogos (útil para continuar de onde parou)')

    def _ensure_stores_exist(self):
        """Garante que as lojas suportadas existam no banco antes de começar."""
        self.stdout.write("Verificando cadastro de lojas...")
        for igdb_id, data in self.IGDB_STORE_MAP.items():
            Store.objects.get_or_create(
                slug=data['slug'],
                defaults={
                    'name': data['name'],
                    'igdb_category_id': igdb_id
                }
            )

    def handle(self, *args, **options):
        start_time = time.time()
        amount = options['amount']
        offset = options['offset']
        
        # 1. Setup Inicial
        self._ensure_stores_exist()
        
        # Carrega lojas do banco para acesso rápido (evita queries no loop)
        # Cria um dict: {1: <Store Object Steam>, 5: <Store Object GOG>, ...}
        active_stores = {
            s.igdb_category_id: s 
            for s in Store.objects.filter(igdb_category_id__isnull=False)
        }

        self.stdout.write(self.style.MIGRATE_HEADING(f" Iniciando Seed: {amount} jogos (Offset: {offset})..."))

        # 2. Definição da Query IGDB
        # Buscamos jogos populares, mas filtramos para ter certeza que é jogo principal, DLC ou Expansão.
        # category = (0, 1, 2, 4, 8, 9, 10) cobre Main, DLC, Expansion, Remake, Remaster, etc.
        # external_games.category IN (...) garante que só pegamos jogos que estão nas lojas que nos importam.
        store_ids = ",".join(map(str, self.IGDB_STORE_MAP.keys()))
        
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
            "external_games.category, external_games.uid"
        )

        # Batch Size do IGDB é max 500. Vamos de 50 para ser seguro e ver progresso.
        batch_size = 50
        processed_count = 0

        while processed_count < amount:
            current_limit = min(batch_size, amount - processed_count)
            current_offset = offset + processed_count
            
            body = f"""
                fields {fields};
                where (category = (0,8,9,10,1,2,4)) & (external_games.category = ({store_ids})) & (total_rating_count > 5);
                sort total_rating_count desc;
                limit {current_limit};
                offset {current_offset};
            """

            data = igdb_api_request('games', body)
            
            if not data:
                self.stdout.write(self.style.WARNING("Nenhum dado retornado ou fim da lista."))
                break

            # 3. Processamento dos Jogos
            for game_data in data:
                try:
                    with transaction.atomic(): # SEGURANÇA: Tudo ou Nada para cada jogo
                        
                        # A. Salva/Atualiza MasterGame
                        master_game, created = _process_and_save_game(game_data)
                        
                        action = "CRIADO" if created else "ATUALIZADO"
                        store_links_added = 0

                        # B. Processa Vínculos com Lojas (GameStoreLink)
                        external_games = game_data.get('external_games', [])
                        if external_games:
                            for ext in external_games:
                                cat_id = ext.get('category')
                                ext_uid = ext.get('uid')
                                
                                # Se é uma loja que monitoramos E temos o objeto Store
                                if cat_id in active_stores and ext_uid:
                                    store_obj = active_stores[cat_id]
                                    
                                    # Cria o link se não existir
                                    _, link_created = GameStoreLink.objects.get_or_create(
                                        master_game=master_game,
                                        store=store_obj,
                                        external_id=ext_uid
                                    )
                                    if link_created:
                                        store_links_added += 1

                        # Feedback visual limpo
                        msg = f"[{action}] {master_game.title[:40]:<40} | Links: {store_links_added}"
                        if created:
                            self.stdout.write(self.style.SUCCESS(msg))
                        else:
                            self.stdout.write(msg) # Texto padrão para updates

                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"Erro ao processar jogo ID {game_data.get('id')}: {e}"))
            
            processed_count += len(data)
            time.sleep(0.5) # Respeito ao Rate Limit (mesmo com retry, bom ter)

        duration = time.time() - start_time
        self.stdout.write(self.style.SUCCESS(f"\nConcluído! {processed_count} jogos processados em {duration:.2f}s."))
