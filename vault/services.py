import re
import nh3
import requests
import random
import time
from datetime import datetime
from django.utils.text import slugify
from django.utils.dateparse import parse_date
from decouple import config
from .models import MasterGame
from bs4 import BeautifulSoup
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
    
    master, created = _process_and_save_game(data)
    return master

class BackloggdScraperService:
    """
    Scraper especializado em Backloggd.
    Estratégia:
    1. Acessa /u/{username}/games para pegar ID, Título, Poster.
    2. Acessa /u/{username}/reviews para pegar textos ricos e spoilers.
    """
    BASE_URL = "https://www.backloggd.com"
    
    def __init__(self, job_id):
        from .models import ProfileImportJob # Import local para evitar ciclo
        self.job = ProfileImportJob.objects.get(id=job_id)
        self.user = self.job.user
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://www.backloggd.com/',
        })

    def run(self):
        try:
            self.job.status = 'processing'
            self.job.save()
            
            # Passo 1: Descobrir total de páginas (meta-dado aproximado)
            self._log("Iniciando varredura de Reviews...")
            self._scrape_reviews()
            
            # Passo 2: Varredura de Library (Jogados mas sem review escrita)
            # self._scrape_library() # (Opcional: implemente se quiser apenas status sem texto)
            
            self.job.status = 'completed'
            self.job.progress_current = self.job.progress_total
            self.job.log_message += "\nImportação finalizada com sucesso."
            self.job.save()
            
        except Exception as e:
            self.job.status = 'failed'
            self.job.log_message = str(e)
            self.job.save()
            raise e

    def _scrape_reviews(self):
        page = 1
        has_next = True
        
        while has_next:
            url = f"{self.BASE_URL}/u/{self.job.target_username}/reviews/page/{page}"
            self._log(f"Lendo página {page}...")
            
            response = self._make_request(url)
            if not response: 
                break
                
            soup = BeautifulSoup(response.text, 'html.parser')
            review_cards = soup.select('div.review-card')
            
            if not review_cards:
                has_next = False
                break
                
            self.job.progress_total += len(review_cards)
            self.job.save()

            for card in review_cards:
                self._process_review_card(card)
                self.job.progress_current += 1
                self.job.save()

            # Paginação check
            next_btn = soup.select_one('nav.pagination a[rel="next"]')
            if not next_btn:
                has_next = False
            
            page += 1
            time.sleep(random.uniform(2.0, 4.0)) # Delay anti-ban

    def _process_review_card(self, card):
        from .models import MasterGame, Platform, PlatformGame, UserLibraryEntry, Review
        
        # 1. Extração de Dados do HTML
        # O Backloggd geralmente esconde o IGDB ID no link da imagem ou atributos data
        # Fallback: Pegar do link do poster
        game_link = card.select_one('.review-card-top a')
        if not game_link: return

        # Tentar extrair IGDB ID do atributo game_id na div.poster (se disponível no card de review)
        # Nota: No card de review as vezes não tem o game_id explícito, mas no link da imagem sim.
        slug = game_link['href'].split('/games/')[1].split('/')[0]
        
        # Título
        # O título as vezes não está texto puro no card de review mobile, mas no alt da imagem
        img_tag = card.select_one('.card-img-top')
        title = img_tag['alt'] if img_tag else slug.replace('-', ' ').title()
        
        # Rating (Width: 80%)
        rating = None
        stars = card.select_one('.stars-top')
        if stars and 'style' in stars.attrs:
            width_match = re.search(r'width:(\d+)%', stars['style'])
            if width_match:
                rating = int(width_match.group(1))

        # Texto e Spoiler
        review_body = card.select_one('.review-body .card-text')
        is_spoiler = bool(card.select('.review-spoiler'))
        
        # Se for spoiler, o texto pode estar escondido ou precisar de clique. 
        # O Backloggd renderiza o texto no HTML mesmo se for spoiler.
        raw_text = review_body.get_text('\n', strip=True) if review_body else ""
        
        # Data
        date_elem = card.select_one('.review-date')
        review_date = None
        if date_elem:
            clean_date = date_elem.get_text(strip=True).replace('Reviewed on ', '')
            try:
                review_date = datetime.strptime(clean_date, '%d %b %Y').date()
            except: pass

        # 2. Resolução do Master Game (CRÍTICO)
        # Tenta achar por slug ou criar Stub
        master_game = MasterGame.objects.filter(slug=slug).first()
        
        if not master_game:
            # Criação de Stub Inteligente
            # Usamos um ID negativo temporário baseado no hash do slug para consistência
            temp_id = -(abs(hash(slug)) % 100000000)
            master_game = MasterGame.objects.create(
                slug=slug,
                title=title,
                igdb_id=temp_id,
                cover_url=img_tag['src'] if img_tag else None
            )
            # Agenda enriquecimento real via IGDB
            # (Pode-se chamar fetch_and_update_game aqui se não for travar muito)

        # 3. Plataforma (Default PC se não soubermos)
        plat_pc, _ = Platform.objects.get_or_create(slug='pc', defaults={'name': 'PC'})
        p_game, _ = PlatformGame.objects.get_or_create(
            master_game=master_game,
            platform=plat_pc, # Backloggd reviews genéricas não mostram plataforma fácil
            defaults={'external_id': f"bl_import_{slug}", 'external_title': title}
        )

        # 4. Persistência (Atomic)
        with transaction.atomic():
            # Library Entry
            entry, created = UserLibraryEntry.objects.get_or_create(
                user=self.user,
                platform_game=p_game
            )
            
            # Atualiza dados se for novo ou se a importação for autoritativa
            entry.status = 'completed' # Se tem review, completou
            if rating:
                entry.rating = rating
            if review_date:
                entry.last_played = review_date # Melhor estimativa
            entry.save()

            # Review
            if raw_text:
                Review.objects.update_or_create(
                    user=self.user,
                    library_entry=entry,
                    defaults={
                        'text': nh3.clean(raw_text), # Sanitização NH3 OBRIGATÓRIA
                        'rating': rating,
                        'contains_spoilers': is_spoiler,
                        'created_at': review_date or datetime.now()
                    }
                )

    def _make_request(self, url):
        try:
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 429:
                self._log("Rate Limit (429). Dormindo 60s...")
                time.sleep(60)
                return self._make_request(url) # Retry
            return resp
        except Exception as e:
            self._log(f"Erro de request: {e}")
            return None

    def _log(self, msg):
        # Atualiza log no banco para o usuário ver se travou
        self.job.log_message = (self.job.log_message + f"\n[{datetime.now().strftime('%H:%M:%S')}] {msg}")[-2000:]
        self.job.save(update_fields=['log_message'])


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
    # --- CORREÇÃO OBRIGATÓRIA AQUI ---
    # Se data for uma lista (ex: [{...}]), pegamos o primeiro item.
    if isinstance(data, list):
        if not data: return None, False # Lista vazia, sai fora
        data = data[0] # Transforma lista em dicionário
    # ---------------------------------

    # Agora data é um dicionário {}, então .get() vai funcionar!
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
    return master_game, created
