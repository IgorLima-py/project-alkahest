import requests
import nh3
import re
from datetime import datetime
from decouple import config
from django.utils.text import slugify
from .models import MasterGame, GameCategory, GameStatus
from .utils_igdb import get_igdb_token

def fetch_and_update_game(igdb_id=None, search_name=None, steam_id=None):
    """
    Busca Jogo no IGDB (Cascata de Tentativas).
    """
    token = get_igdb_token()
    if not token: return None

    client_id = config('TWITCH_CLIENT_ID')
    headers = {'Client-ID': client_id, 'Authorization': f'Bearer {token}'}
    
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
        "websites.url, websites.category"
    )

    data = []

    # 1. TENTATIVA: ID IGDB DIRETO
    if igdb_id:
        query = f'fields {fields}; where id = {igdb_id};'
        data = _igdb_request(query, headers)

    # 2. TENTATIVA: STEAM ID (Link Oficial)
    if not data and steam_id:
        # Category 13 = Steam. Tenta achar o jogo exato linkado.
        query = f'fields {fields}; where external_games.uid = "{steam_id}" & external_games.category = 13; limit 1;'
        data = _igdb_request(query, headers)

    if not data and search_name:
        # Limpeza básica de segurança (tira aspas)
        safe_name_raw = search_name.replace('"', '').replace(';', '')

        # 3. TENTATIVA: NOME EXATO (Como veio da Steam)
        # Ex: "The Witcher: Enhanced Edition Director's Cut"
        # Pode falhar se o IGDB não tiver "Director's Cut" no nome.
        query = f'search "{safe_name_raw}"; fields {fields}; limit 1;'
        data = _igdb_request(query, headers)

        # 4. TENTATIVA: NOME "LEVE" (Remove lixo, mas MANTE EDIÇÃO)
        # Transforma "Rainbow Six® Siege X" -> "Rainbow Six Siege"
        # Transforma "Witcher: EE Director's Cut" -> "Witcher: EE"
        if not data:
            semi_clean = _sanitize_light(safe_name_raw)
            if semi_clean != safe_name_raw:
                print(f"   (Service) Tentando nome ajustado: '{semi_clean}'")
                query = f'search "{semi_clean}"; fields {fields}; limit 1;'
                data = _igdb_request(query, headers)

        # 5. TENTATIVA: NOME "BASE" (Remove Edição) -> Último recurso
        # Transforma "Witcher: Enhanced Edition" -> "Witcher"
        # Só pra garantir que não fica sem capa.
        if not data:
            base_clean = _sanitize_heavy(safe_name_raw)
            if base_clean != semi_clean and base_clean != safe_name_raw:
                print(f"   (Service) Fallback para jogo base: '{base_clean}'")
                query = f'search "{base_clean}"; fields {fields}; limit 1;'
                data = _igdb_request(query, headers)

    if not data or 'id' not in data[0]: return None
    
    return _process_and_save_game(data[0])

def _igdb_request(body, headers):
    try:
        response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=body)
        res_json = response.json()
        if isinstance(res_json, list) and res_json: return res_json
        return []
    except: return []

def _sanitize_light(name):
    """Limpa apenas lixo (símbolos, 'Director's Cut', 'X'), mantendo GOTY/Enhanced"""
    # 1. Remove TM, R, Copyright
    name = re.sub(r'[®™©]', '', name)
    
    # 2. Remove sufixos que geralmente atrapalham a busca exata no IGDB
    # "Director's Cut" as vezes atrapalha se o IGDB cadastrou só "Enhanced Edition"
    useless_suffixes = [
        r'\s*director\'s cut.*', 
        r'\s*digital deluxe.*', 
        r'\s*premium edition.*',
        r'\s*bonus edition.*',
        r'\s+X$' # O caso do Rainbow Six Siege X
    ]
    for suffix in useless_suffixes:
        name = re.sub(suffix, '', name, flags=re.IGNORECASE)
    
    return name.strip()

def _sanitize_heavy(name):
    """Limpeza agressiva para achar o jogo base (Fallback final)"""
    name = _sanitize_light(name) # Começa limpando o lixo
    
    # Remove as edições principais para sobrar só o título base
    edition_suffixes = [
        r'\s*goty.*', r'\s*game of the year.*', 
        r'\s*enhanced edition.*', 
        r'\s*remastered.*', r'\s*remake.*',
        r'\s*complete edition.*',
        r'\s*bundle.*'
    ]
    for suffix in edition_suffixes:
        name = re.sub(suffix, '', name, flags=re.IGNORECASE)

    return name.strip()

def _process_and_save_game(data):
    """Parsing robusto dos novos campos com proteção de Foreign Key"""
    
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

    # Proteção de Foreign Key
    parent_obj = None
    igdb_parent_id = data.get('parent_game')
    if igdb_parent_id:
        try:
            parent_obj = MasterGame.objects.get(igdb_id=igdb_parent_id)
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