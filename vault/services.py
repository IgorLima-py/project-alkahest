import requests
import nh3
from datetime import datetime
from decouple import config
from django.utils.text import slugify
from django.db.models import Sum, Count # Imports que seu Radar usava
from .models import MasterGame, GameCategory, UserAchievement, Review, GameTip, UserLibraryEntry
from .utils_igdb import get_igdb_token

# ==========================================
# SERVIÇO 1: INTEGRAÇÃO IGDB (IMPORTAÇÃO)
# ==========================================

def fetch_and_update_game(igdb_id=None, search_name=None, steam_id=None):
    """
    Busca um jogo no IGDB.
    Prioridade: IGDB ID > Steam ID > Nome
    """
    token = get_igdb_token()
    if not token: return None

    client_id = config('TWITCH_CLIENT_ID')
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {token}'}
    
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

    query_body = ""
    
    if igdb_id:
        query_body = f'fields {fields}; where id = {igdb_id};'
    elif steam_id:
        # BUSCA INFALÍVEL: Pede o jogo que tem esse ID na Steam (category 13)
        query_body = f'fields {fields}; where external_games.uid = "{steam_id}" & external_games.category = 13; limit 1;'
    elif search_name:
        safe_name = search_name.replace('"', '').replace(';', '') 
        query_body = f'search "{safe_name}"; fields {fields}; limit 1;'
    
    if not query_body: return None

    try:
        response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=query_body)
        data = response.json()
        
        # Se buscou por Steam ID e não achou, tenta fallback por nome se fornecido
        if not data and steam_id and search_name:
             safe_name = search_name.replace('"', '').replace(';', '') 
             query_body = f'search "{safe_name}"; fields {fields}; limit 1;'
             response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=query_body)
             data = response.json()

        if not data or 'id' not in data[0]: return None
        
        return _process_and_save_game(data[0])

    except Exception as e:
        print(f"Erro no Service IGDB: {e}")
        return None

def _process_and_save_game(data):
    """Parsing robusto dos novos campos"""
    
    # 1. Imagens (Prioriza Artwork para background, se não tiver, usa Screenshot)
    cover_url = 'https:' + data['cover']['url'].replace('t_thumb', 't_cover_big') if 'cover' in data else None
    
    artworks = ['https:' + img['url'].replace('t_thumb', 't_1080p') for img in data.get('artworks', [])]
    screenshots = ['https:' + img['url'].replace('t_thumb', 't_1080p') for img in data.get('screenshots', [])]
    
    # Lógica da capa de fundo (Hero): Tenta Artwork -> Screenshot -> Capa normal
    background_url = artworks[0] if artworks else (screenshots[0] if screenshots else cover_url)

    videos = [v['video_id'] for v in data.get('videos', [])] # IDs do Youtube

    # 2. Listas de Texto Simples
    genres = [x['name'] for x in data.get('genres', [])]
    themes = [x['name'] for x in data.get('themes', [])]
    modes = [x['name'] for x in data.get('game_modes', [])]
    perspectives = [x['name'] for x in data.get('player_perspectives', [])]
    engines = [x['name'] for x in data.get('game_engines', [])]
    franchises = [x['name'] for x in data.get('franchises', [])]
    collection = data.get('collection', {}).get('name') # Série (ex: Uncharted Collection)

    # 3. Relações (IDs)
    similar_ids = data.get('similar_games', []) # Lista de IDs (Int)
    dlc_ids = data.get('dlcs', []) # Lista de IDs (Int)

    # 4. Processamento de Idiomas (Transformar a bagunça do IGDB em algo legível)
    languages = {"Audio": [], "Subtitles": [], "Interface": []}
    if 'language_supports' in data:
        for lang_obj in data['language_supports']:
            try:
                l_name = lang_obj.get('language', {}).get('name')
                l_type = lang_obj.get('language_support_type', {}).get('name') # Audio, Subtitles, Interface
                if l_name and l_type:
                    if l_type in languages:
                        languages[l_type].append(l_name)
            except: continue
    # Remove duplicatas
    for k in languages: languages[k] = list(set(languages[k]))

    # 5. Companies
    developers = []
    publishers = []
    for involved in data.get('involved_companies', []):
        c_name = involved.get('company', {}).get('name')
        if c_name:
            if involved.get('developer'): developers.append(c_name)
            if involved.get('publisher'): publishers.append(c_name)

    # 6. Salvar
    master_game, created = MasterGame.objects.update_or_create(
        igdb_id=data['id'],
        defaults={
            'title': data['name'],
            'slug': data.get('slug', slugify(data['name'])),
            'status': data.get('status', 0), # 0 = Released
            'summary': nh3.clean(data.get('summary', '')),
            'storyline': nh3.clean(data.get('storyline', '')),
            'release_date': datetime.fromtimestamp(data['first_release_date']).date() if 'first_release_date' in data else None,
            
            # Imagens
            'cover_url': cover_url,
            'background_url': background_url,
            'artworks': artworks,
            'screenshots': screenshots,
            'videos': videos,
            
            # Dados Ricos
            'developers': developers,
            'publishers': publishers,
            'game_engines': engines,
            'genres': genres,
            'themes': themes,
            'game_modes': modes,
            'player_perspectives': perspectives,
            'collection': collection,
            'franchises': franchises,
            'similar_games': similar_ids,
            'dlcs': dlc_ids,
            'supported_languages': languages,
            
            # Hierarquia
            'category': data.get('category', 0),
            'parent_id': data.get('parent_game'),
        }
    )
    
    # Nota: External IDs eu mantive a lógica simplificada anterior, 
    # se quiser adicionar mais sites (Twitch, Wikipedia), é só expandir o loop de websites.
    
    return master_game


# ==========================================
# SERVIÇO 2: LÓGICA DE NEGÓCIO (RADAR/STATS)
# ==========================================

class RadarChartService:
    def __init__(self, user):
        self.user = user

    def calculate_stats(self):
        """
        Calcula os 5 pilares do Death Stranding Chart.
        """
        stats = {
            'volume': 0, 'skill': 0, 'variety': 0, 'social': 0, 'speed': 0
        }

        # 1. VOLUME (XP)
        total_xp = UserAchievement.objects.filter(user=self.user).aggregate(Sum('achievement__xp_value'))['achievement__xp_value__sum'] or 0
        stats['volume'] = min((total_xp / 100000) * 100, 100)

        # 2. SKILL (% Completude)
        games_started = UserLibraryEntry.objects.filter(user=self.user, status__in=['playing', 'completed', 'dropped'])
        completed_count = games_started.filter(status='completed').count()
        total_started = games_started.count()
        if total_started > 0:
            stats['skill'] = (completed_count / total_started) * 100

        # 3. VARIETY (Gêneros únicos)
        # Agora que temos genres no MasterGame, podemos calcular de verdade!
        # Isso é um pouco pesado, melhor fazer via SQL puro ou denormalização futura,
        # mas por enquanto, Python set resolve para volumes baixos.
        entries = UserLibraryEntry.objects.filter(user=self.user).select_related('platform_game__master_game')
        unique_genres = set()
        for entry in entries:
            for g in entry.platform_game.master_game.genres:
                unique_genres.add(g)
        
        # Digamos que 10 gêneros diferentes = 100% variety
        stats['variety'] = min((len(unique_genres) / 10) * 100, 100)

        # 4. SOCIAL
        review_likes = Review.objects.filter(user=self.user).aggregate(Sum('likes_count'))['likes_count__sum'] or 0
        tip_upvotes = GameTip.objects.filter(user=self.user).aggregate(Sum('upvotes'))['upvotes__sum'] or 0
        total_social = review_likes + tip_upvotes
        stats['social'] = min((total_social / 500) * 100, 100)

        return stats