import re
import time
import random
import requests
import nh3
import cloudscraper  # pip install cloudscraper
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
    Busca Jogo no IGDB (Cascata de Tentativas) e retorna objeto MasterGame salvo.
    """
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

    # 2. TENTATIVA: STEAM ID
    if not data and steam_id:
        body = f"fields {fields}; where external_games.uid = \"{steam_id}\" & external_games.category = 13; limit 1;"
        data = igdb_api_request('games', body)

    if not data and search_name:
        safe_name_raw = search_name.replace('"', '').replace(';', '')

        # 3. TENTATIVA: NOME EXATO
        body = f"search \"{safe_name_raw}\"; fields {fields}; limit 1;"
        data = igdb_api_request('games', body)

        # 4. TENTATIVA: NOME LEVE
        if not data:
            semi_clean = _sanitize_light(safe_name_raw)
            if semi_clean != safe_name_raw:
                print(f"   (Service) Tentando nome ajustado: '{semi_clean}'")
                body = f"search \"{semi_clean}\"; fields {fields}; limit 1;"
                data = igdb_api_request('games', body)

        # 5. TENTATIVA: NOME BASE
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
    if isinstance(data, list):
        if not data: return None, False 
        data = data[0]

    # FIX: Garante URL https e imagem grande
    cover_url = None
    if 'cover' in data and 'url' in data['cover']:
        cover_url = 'https:' + data['cover']['url'].replace('t_thumb', 't_cover_big') 
        if not cover_url.startswith('https:https:'): # Fix para caso a URL já venha com protocolo
             pass # ok
        else:
             cover_url = cover_url.replace('https:////', 'https://') # Fix urls malucas do igdb

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
            # Tenta pegar apenas se já existir localmente para evitar recursão infinita
            parent_obj = MasterGame.objects.filter(igdb_id=data['parent_game']).first()
        except:
            pass 

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
# BLOCO 2: BACKLOGGD SCRAPER SERVICE (Mantido Intacto)
# ==============================================================================

class BackloggdScraperService:
    BASE_URL = "https://www.backloggd.com"
    
    def __init__(self, job_id):
        from .models import ProfileImportJob
        self.job = ProfileImportJob.objects.get(id=job_id)
        self.user = self.job.user
        
        self.scraper = cloudscraper.create_scraper(
            browser={
                'browser': 'chrome',
                'platform': 'android', 
                'mobile': True
            }
        )

    def run(self):
        try:
            self.job.status = 'processing'
            self.job.save()
            self._log(f"Iniciando importação para: {self.job.target_username}")
            
            count_log = self._scrape_log()
            
            if count_log == 0:
                self.job.status = 'failed'
                self.job.log_message += "\n❌ Nenhum log encontrado. Perfil privado ou sem diário."
            else:
                self.job.status = 'completed'
                self.job.log_message += f"\n✅ Sucesso! {count_log} logs processados."
            
            self.job.progress_current = self.job.progress_total
            self.job.save()
            return count_log
            
        except Exception as e:
            self.job.status = 'failed'
            self.job.log_message = f"❌ Erro Fatal: {str(e)}"
            self.job.save()
            print(f"Erro no Scraper: {e}")
            return 0

    def _scrape_log(self):
        page = 1
        total_extracted = 0
        
        while True:
            url = f"{self.BASE_URL}/u/{self.job.target_username}/log/page/{page}/"
            self._log(f"📖 Lendo Diário (Log) pg {page}...")
            
            response = self._make_request(url)
            if not response or response.status_code == 404: break
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            log_entries = soup.select('div.log-entry, div.journal-entry, div.card-log')
            
            if not log_entries:
                log_entries = soup.select('div[data-rating]')
            
            self._log(f"   Encontrados {len(log_entries)} logs.")
            
            if not log_entries: break

            self.job.progress_total += len(log_entries)
            self.job.save()

            for entry in log_entries:
                try:
                    self._process_log_entry(entry)
                    self.job.progress_current += 1
                    total_extracted += 1
                    self.job.save()
                except Exception as e:
                    print(f"Skip: {e}")

            if not soup.find('a', attrs={'rel': 'next'}): break
            page += 1
            time.sleep(random.uniform(2, 5)) 
            
        return total_extracted

    def _process_log_entry(self, card):
        link = card.select_one('a[href*="/games/"]')
        if not link: return
        
        href = link['href']
        try:
            slug = href.split('/games/')[1].split('/')[0]
        except: return
        
        img = card.find('img')
        title = img.get('alt') if img else link.get_text(strip=True)
        cover_url = img.get('src') if img else None
        if not title: title = slug.replace('-', ' ').title()

        rating = None
        data_rating = card.get('data-rating')
        if data_rating:
            rating = int(data_rating) * 10 
        else:
            stars = card.select_one('.stars-top')
            if stars:
                width = re.search(r'width:\s*(\d+)%', stars.get('style', ''))
                if width: rating = int(width.group(1))

        review_text = ""
        review_div = card.select_one('.journal-review, .log-review, .review-text, .card-text')
        
        if review_div:
            review_text = review_div.get_text('\n', strip=True)
        else:
            ps = card.select('p')
            for p in ps:
                txt = p.get_text(strip=True)
                if len(txt) > 20 and "Played on" not in txt and "Review by" not in txt:
                    review_text = txt
                    break
        
        if len(review_text) < 10: review_text = ""

        is_spoiler = bool(card.select_one('.spoiler'))

        self._save_to_db(slug, title, cover_url, rating, review_text, is_spoiler)

    def _save_to_db(self, slug, title, cover_url, rating, text, is_spoiler):
        temp_id = -(abs(hash(slug)) % 9999999)
        
        master, _ = MasterGame.objects.get_or_create(
            slug=slug,
            defaults={
                'title': title,
                'igdb_id': temp_id,
                'cover_url': cover_url,
                'status': 0
            }
        )
        
        pc, _ = Platform.objects.get_or_create(slug='pc', defaults={'name': 'PC'})
        
        pg, _ = PlatformGame.objects.get_or_create(
            master_game=master, platform=pc,
            defaults={'external_id': f"bl_{slug}", 'external_title': title}
        )
        
        with transaction.atomic():
            entry, _ = UserLibraryEntry.objects.get_or_create(
                user=self.user, platform_game=pg,
                defaults={'status': 'completed'}
            )
            
            if rating:
                entry.rating = rating
                entry.save()
            
            if text:
                Review.objects.update_or_create(
                    user=self.user, library_entry=entry,
                    defaults={
                        'text': nh3.clean(text),
                        'rating': rating,
                        'contains_spoilers': is_spoiler,
                        'title': f"Review de {title}"
                    }
                )

    def _make_request(self, url, retries=3): 
        try:
            if retries <= 0:
                self._log("❌ Limite de tentativas excedido.")
                return None

            resp = self.scraper.get(url, timeout=20)
            
            if resp.status_code == 429:
                self._log(f"⏳ Rate Limit (429). Tentativas restantes: {retries}")
                time.sleep(60)
                return self._make_request(url, retries=retries - 1)
            
            return resp
        except Exception as e:
            self._log(f"Erro de conexão: {e}")
            return None

    def _log(self, msg):
        print(f"[Import] {msg}")
        ts = datetime.now().strftime("%H:%M:%S")
        self.job.log_message = f"{self.job.log_message}\n[{ts}] {msg}"[-2000:]
        self.job.save(update_fields=['log_message'])
