# vault/services.py
import re
import time
import random
import requests
import nh3
import cloudscraper  # <--- CRÍTICO: Instale com 'pip install cloudscraper'
from bs4 import BeautifulSoup
from datetime import datetime

from django.utils.text import slugify
from django.utils.dateparse import parse_date
from django.db import transaction
from decouple import config

from .models import MasterGame, Platform, PlatformGame, UserLibraryEntry, Review
from .utils_igdb import igdb_api_request 

# ==============================================================================
# BLOCO 1: LÓGICA IGDB (FETCH & UPDATE)
# ==============================================================================

def fetch_and_update_game(igdb_id=None, search_name=None, steam_id=None):
    """
    Busca Jogo no IGDB (Cascata de Tentativas) usando o wrapper robusto.
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
        "external_games.category, external_games.uid" 
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

# --- Funções Auxiliares IGDB ---

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

def _process_and_save_game(data):
    # Se data for uma lista (ex: [{...}]), pegamos o primeiro item.
    if isinstance(data, list):
        if not data: return None, False 
        data = data[0]

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


# ==============================================================================
# BLOCO 2: BACKLOGGD SCRAPER SERVICE (CLOUD SCRAPER EDITION)
# ==============================================================================

class BackloggdScraperService:
    """
    Scraper robusto para Backloggd usando CloudScraper para bypass de Cloudflare.
    Estratégia:
    - Simula um browser real (Chrome/Windows).
    - Link-First Strategy: Busca links de jogos e sobe a hierarquia DOM para achar dados.
    """
    BASE_URL = "https://www.backloggd.com"
    
    def __init__(self, job_id):
        from .models import ProfileImportJob
        self.job = ProfileImportJob.objects.get(id=job_id)
        self.user = self.job.user
        
        # Inicializa o CloudScraper em vez de Requests simples
        # Isso resolve os erros de 403/429 e CAPTCHA oculto
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'windows',
                'desktop': True
            }
        )

    def run(self):
        try:
            self.job.status = 'processing'
            self.job.save()
            
            self._log(f"Iniciando importação para: {self.job.target_username}")
            
            # Scrape de Reviews (Conteúdo mais rico)
            total_reviews = self._scrape_reviews()
            
            # Scrape de Jogados (Opcional - Fase futura)
            # self._scrape_games_list() 
            
            if total_reviews == 0:
                self.job.status = 'failed'
                self.job.log_message += "\n❌ Nenhum item encontrado. Perfil privado ou bloqueio severo."
            else:
                self.job.status = 'completed'
                self.job.log_message += f"\n✅ Sucesso! {total_reviews} reviews importadas."
            
            self.job.progress_current = self.job.progress_total
            self.job.save()
            
        except Exception as e:
            self.job.status = 'failed'
            self.job.log_message = f"❌ Erro Fatal: {str(e)}"
            self.job.save()
            # Não damos raise para não crashar o Celery, apenas marcamos o job como falha
            print(f"Erro no Scraper: {e}")

    def _scrape_reviews(self):
        page = 1
        total_extracted = 0
        
        while True:
            url = f"{self.BASE_URL}/u/{self.job.target_username}/reviews/page/{page}/"
            self._log(f"📖 Lendo página {page}...")
            
            response = self._make_request(url)
            if not response or response.status_code == 404:
                break
                
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # ESTRATÉGIA LINK-FIRST
            # Encontra todos os links de jogos e deduz o card pai
            links = soup.select('a[href*="/games/"]')
            
            unique_items = []
            seen_slugs = set()
            
            for link in links:
                # Sobe para achar o container (card ou coluna)
                card = link.find_parent('div', class_='card') or link.find_parent('div', class_='col-12')
                
                if card:
                    href = link['href']
                    # Extrai slug da URL: /games/elden-ring/ -> elden-ring
                    try:
                        parts = [p for p in href.split('/') if p]
                        if 'games' in parts:
                            slug_idx = parts.index('games') + 1
                            if slug_idx < len(parts):
                                slug = parts[slug_idx]
                                
                                if slug not in seen_slugs:
                                    seen_slugs.add(slug)
                                    unique_items.append((card, slug, link))
                    except: continue

            self._log(f"   Encontrados {len(unique_items)} itens.")
            
            if not unique_items:
                break # Página vazia ou fim da lista
                
            self.job.progress_total += len(unique_items)
            self.job.save()

            for item in unique_items:
                try:
                    self._process_item(item)
                    self.job.progress_current += 1
                    total_extracted += 1
                    self.job.save()
                except Exception as e:
                    print(f"Erro processando item: {e}")

            # Paginação: Verifica se existe botão Next
            next_btn = soup.find('a', attrs={'rel': 'next'})
            if not next_btn:
                break
                
            page += 1
            time.sleep(random.uniform(2, 5)) # Delay humano
            
        return total_extracted

    def _process_item(self, item):
        card, slug, link_elem = item
        
        # 1. TÍTULO & CAPA
        img = card.find('img')
        title = img.get('alt') if img else link_elem.get_text(strip=True)
        cover_url = img.get('src') if img else None
        
        if not title: title = slug.replace('-', ' ').title()
        
        # 2. RATING (Procura style="width:XX%")
        rating = None
        style_elem = card.find(style=re.compile(r'width:\s*\d+%'))
        if style_elem:
            match = re.search(r'width:\s*(\d+)%', style_elem['style'])
            if match:
                rating = int(match.group(1))
                
        # 3. TEXTO & SPOILER
        review_text = ""
        is_spoiler = bool(card.find(class_='spoiler') or card.find(class_='review-spoiler'))
        
        # Heurística: Review é o texto mais longo do card
        candidates = card.find_all(['p', 'span', 'div'])
        valid_texts = []
        for c in candidates:
            # Ignora classes irrelevantes
            if 'stars' in c.get('class', []) or 'date' in c.get('class', []): continue
            
            text = c.get_text('\n', strip=True)
            if len(text) > 15: # Ignora textos curtos (datas, labels)
                valid_texts.append(text)
        
        if valid_texts:
            review_text = max(valid_texts, key=len)

        # 4. SALVAR
        self._save_to_db(slug, title, cover_url, rating, review_text, is_spoiler)

    def _save_to_db(self, slug, title, cover_url, rating, text, is_spoiler):
        # Master Game Stub (ID Negativo Temporário)
        # Usamos hash do slug para gerar um ID consistente (idempotência)
        temp_id = -(abs(hash(slug)) % 9999999)
        
        master, _ = MasterGame.objects.get_or_create(
            slug=slug,
            defaults={
                'title': title,
                'igdb_id': temp_id,
                'cover_url': cover_url,
                'status': 0 # Released
            }
        )
        
        # Platform (PC Default)
        pc, _ = Platform.objects.get_or_create(slug='pc', defaults={'name': 'PC'})
        
        # Platform Game Link
        pg, _ = PlatformGame.objects.get_or_create(
            master_game=master, platform=pc,
            defaults={'external_id': f"bl_{slug}", 'external_title': title}
        )
        
        with transaction.atomic():
            # Library Entry
            entry, _ = UserLibraryEntry.objects.get_or_create(
                user=self.user, platform_game=pg,
                defaults={'status': 'completed'}
            )
            
            if rating:
                entry.rating = rating
                entry.save()
            
            # Review
            if text:
                Review.objects.update_or_create(
                    user=self.user, library_entry=entry,
                    defaults={
                        'text': nh3.clean(text), # Sanitização NH3
                        'rating': rating,
                        'contains_spoilers': is_spoiler,
                        'title': f"Review de {title}"
                    }
                )

    def _make_request(self, url):
        try:
            # Usa o scraper.get em vez de requests.get
            resp = self.scraper.get(url, timeout=20)
            
            if resp.status_code == 429:
                self._log("⏳ Rate Limit (429). Aguardando 60s...")
                time.sleep(60)
                return self._make_request(url)
                
            return resp
        except Exception as e:
            self._log(f"Erro de conexão: {e}")
            return None

    def _log(self, msg):
        print(f"[Import] {msg}") # Output no terminal
        # Atualiza log no banco
        ts = datetime.now().strftime("%H:%M:%S")
        self.job.log_message = f"{self.job.log_message}\n[{ts}] {msg}"[-2000:]
        self.job.save(update_fields=['log_message'])
