import re
import nh3
from datetime import datetime
from django.utils.text import slugify
from decouple import config
from .models import MasterGame
from .utils_igdb import igdb_api_request # Importa a nova função robusta

def fetch_and_update_game(igdb_id=None, search_name=None, steam_id=None):
    """
    Busca Jogo no IGDB (Cascata de Tentativas) usando o novo wrapper robusto.
    """
    
    # Query de campos completa
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
        "external_games.category, external_games.uid" # Importante para linkar lojas
    )

    data = []

    # 1. TENTATIVA: ID IGDB DIRETO
    if igdb_id:
        body = f"fields {fields}; where id = {igdb_id};"
        data = igdb_api_request('games', body)

    # 2. TENTATIVA: STEAM ID (Link Oficial)
    if not data and steam_id:
        # Category 13 = Steam.
        body = f"fields {fields}; where external_games.uid = \"{steam_id}\" & external_games.category = 13; limit 1;"
        data = igdb_api_request('games', body)

    if not data and search_name:
        safe_name_raw = search_name.replace('"', '').replace(';', '')

        # 3. TENTATIVA: NOME EXATO
        body = f"search \"{safe_name_raw}\"; fields {fields}; limit 1;"
        data = igdb_api_request('games', body)

        # 4. TENTATIVA: NOME "LEVE"
        if not data:
            semi_clean = _sanitize_light(safe_name_raw)
            if semi_clean != safe_name_raw:
                print(f"   (Service) Tentando nome ajustado: '{semi_clean}'")
                body = f"search \"{semi_clean}\"; fields {fields}; limit 1;"
                data = igdb_api_request('games', body)

        # 5. TENTATIVA: NOME "BASE"
        if not data:
            base_clean = _sanitize_heavy(safe_name_raw)
            if base_clean != semi_clean and base_clean != safe_name_raw:
                print(f"   (Service) Fallback para jogo base: '{base_clean}'")
                body = f"search \"{base_clean}\"; fields {fields}; limit 1;"
                data = igdb_api_request('games', body)

    if not data or 'id' not in data[0]: 
        return None
    
    return _process_and_save_game(data[0])

# Funções auxiliares de limpeza (mantidas iguais)
def _sanitize_light(name):
    name = re.sub(r'[®™©]', '', name)
    useless_suffixes = [
        r'\s*director\'s cut.*', r'\s*digital deluxe.*', r'\s*premium edition.*',
        r'\s*bonus edition.*', r'\s+X$'
    ]
    for suffix in useless_suffixes:
        name = re.sub(suffix, '', name, flags=re.IGNORECASE)
    return name.strip()

def _sanitize_heavy(name):
    name = _sanitize_light(name)
    edition_suffixes = [
        r'\s*goty.*', r'\s*game of the year.*', r'\s*enhanced edition.*', 
        r'\s*remastered.*', r'\s*remake.*', r'\s*complete edition.*', r'\s*bundle.*'
    ]
    for suffix in edition_suffixes:
        name = re.sub(suffix, '', name, flags=re.IGNORECASE)
    return name.strip()

# Função de Processamento (Mantida igual mas sem a request dentro)
def _process_and_save_game(data):
    # ... (Copie a sua função _process_and_save_game original para cá, ela está perfeita)
    # ... Apenas certifique-se que ela usa o MasterGame importado lá em cima
    
    # [Vou resumir a parte que não muda para economizar espaço, mas você deve manter tudo]
    cover_url = 'https:' + data['cover']['url'].replace('t_thumb', 't_cover_big') if 'cover' in data else None
    
    artworks = ['https:' + img['url'].replace('t_thumb', 't_1080p') for img in data.get('artworks', [])]
    screenshots = ['https:' + img['url'].replace('t_thumb', 't_1080p') for img in data.get('screenshots', [])]
    background_url = artworks[0] if artworks else (screenshots[0] if screenshots else cover_url)

    videos = [v['video_id'] for v in data.get('videos', [])]
    genres = [x['name'] for x in data.get('genres', [])]
    themes = [x['name'] for x in data.get('themes', [])]
    modes = [x['name'] for x in data.get('game_modes', [])]
    perspectives = [x['name'] for x in data.get('player_perspectives', [])]
    engines = [x['name'] for x in data.get('game_engines', [])]
    franchises = [x['name'] for x in data.get('franchises', [])]
    collection = data.get('collection', {}).get('name')
    similar_ids = data.get('similar_games', []) 
    dlc_ids = data.get('dlcs', [])

    parent_obj = None
    if data.get('parent_game'):
        try:
            parent_obj = MasterGame.objects.get(igdb_id=data['parent_game'])
        except MasterGame.DoesNotExist:
            parent_obj = None 

    languages = {"Audio": [], "Subtitles": [], "Interface": []}
    if 'language_supports' in data:
        for lang_obj in data['language_supports']:
            try:
                l_name = lang_obj.get('language', {}).get('name')
                l_type = lang_obj.get('language_support_type', {}).get('name')
                if l_name and l_type and l_type in languages:
                    languages[l_type].append(l_name)
            except: continue
    for k in languages: languages[k] = list(set(languages[k]))

    developers = []
    publishers = []
    for involved in data.get('involved_companies', []):
        c_name = involved.get('company', {}).get('name')
        if c_name:
            if involved.get('developer'): developers.append(c_name)
            if involved.get('publisher'): publishers.append(c_name)

    master_game, created = MasterGame.objects.update_or_create(
        igdb_id=data['id'],
        defaults={
            'title': data['name'],
            'slug': data.get('slug', slugify(data['name'])),
            'status': data.get('status', 0),
            'summary': nh3.clean(data.get('summary', '')),
            'storyline': nh3.clean(data.get('storyline', '')),
            'release_date': datetime.fromtimestamp(data['first_release_date']).date() if 'first_release_date' in data else None,
            'cover_url': cover_url,
            'background_url': background_url,
            'artworks': artworks,
            'screenshots': screenshots,
            'videos': videos,
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
            'category': data.get('category', 0),
            'parent': parent_obj, 
        }
    )
    return master_game
