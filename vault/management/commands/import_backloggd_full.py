import time
import random
import re
import nh3
import cloudscraper
from datetime import datetime
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from django.contrib.auth.models import User
from vault.models import (
    MasterGame, Platform, PlatformGame, UserLibraryEntry, 
    Review, ProfileImportJob
)

class Command(BaseCommand):
    help = 'Importação Cirúrgica do Backloggd (Logs Completos + Reviews + Datas)'

    def add_arguments(self, parser):
        parser.add_argument('username', type=str, help='Usuário do Backloggd')
        parser.add_argument('--target_user', type=str, help='Username no Alkahest (se diferente)')
        parser.add_argument('--pages', type=int, default=0, help='Quantas páginas importar (0 = todas)')
        parser.add_argument('--fast', action='store_true', help='Pula a extração profunda (só lista, sem texto completo)')

    def handle(self, *args, **options):
        self.backloggd_user = options['username']
        self.target_user_str = options.get('target_user') or self.backloggd_user
        self.max_pages = options['pages']
        self.fast_mode = options['fast']
        
        # Setup Scraper Anti-Bot
        self.scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'android', 'mobile': True})
        
        try:
            self.user = User.objects.get(username=self.target_user_str)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Usuário local '{self.target_user_str}' não encontrado."))
            return

        self.stdout.write(self.style.SUCCESS(f"🚀 Iniciando extração 'Bala de Prata' para: {self.backloggd_user}"))
        self.stdout.write(f"🎯 Modo: {'Rápido (Sem detalhes)' if self.fast_mode else 'Profundo (Extração Full)'}")

        # Loop Principal
        page = 1
        total_processed = 0
        
        while True:
            if self.max_pages > 0 and page > self.max_pages:
                break
                
            url = f"https://www.backloggd.com/u/{self.backloggd_user}/log/page/{page}/"
            self.stdout.write(f"\n📄 Processando página {page}...")
            
            resp = self._make_request(url)
            if not resp: break
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            logs = soup.select('div.log-entry, div.journal-entry')
            
            if not logs:
                self.stdout.write(self.style.WARNING("⚠️ Fim da linha ou página vazia."))
                break
                
            for card in logs:
                try:
                    self._process_card(card)
                    total_processed += 1
                except Exception as e:
                    self.stdout.write(self.style.ERROR(f"❌ Erro no card: {e}"))
            
            # Paginação check
            if not soup.find('a', attrs={'rel': 'next'}):
                self.stdout.write("✅ Fim da paginação.")
                break
                
            page += 1
            # Delay humano entre páginas (essencial)
            time.sleep(random.uniform(2, 4))

        self.stdout.write(self.style.SUCCESS(f"\n🏁 Processo finalizado! {total_processed} entradas processadas."))

    def _process_card(self, card):
        # 1. Extração Básica (Listagem)
        game_link = card.select_one('a[href*="/games/"]')
        if not game_link: return
        
        raw_slug = game_link['href'].split('/games/')[1].split('/')[0]
        title = game_link.get_text(strip=True) or raw_slug.replace('-', ' ').title()
        
        # Capa
        img = card.find('img')
        cover_url = img.get('src') if img else None
        
        # Rating (Estrelas ou numérico)
        rating = None
        stars_div = card.select_one('.stars-top')
        if stars_div:
            width_str = re.search(r'width:\s*(\d+)%', stars_div.get('style', ''))
            if width_str: rating = int(width_str.group(1))
            
        # Data do Log (Importante para diferenciar duplicatas!)
        log_date = None
        date_elem = card.select_one('.log-date, .journal-date')
        if date_elem:
            date_str = date_elem.get_text(strip=True)
            try:
                # Formato comum: "Feb 01, 2026"
                log_date = datetime.strptime(date_str, "%b %d, %Y").date()
            except ValueError:
                log_date = datetime.now().date() # Fallback

        # Identificar Review
        review_link_elem = card.select_one('a[href*="/review/"]')
        review_url = None
        full_text = ""
        is_spoiler = False
        platform_name = "PC" # Default
        
        if review_link_elem:
            review_url = "https://www.backloggd.com" + review_link_elem['href']

        # 2. Extração Profunda (Entrar na Review)
        # Só entra se tiver link de review E não estivermos no modo rápido
        if review_url and not self.fast_mode:
            self.stdout.write(f"  ↳ 🕵️ Extraindo detalhes de: {title}...", ending='')
            time.sleep(random.uniform(1.0, 2.5)) # Delay crítico
            
            details = self._fetch_review_details(review_url)
            if details:
                full_text = details.get('text', '')
                is_spoiler = details.get('spoiler', False)
                if details.get('platform'):
                    platform_name = details.get('platform')
                self.stdout.write(" OK")
            else:
                self.stdout.write(" Falha no detail")
        else:
            # Tenta pegar texto truncado da lista se existir
            text_div = card.select_one('.journal-review p')
            if text_div: full_text = text_div.get_text(strip=True)

        # 3. Persistência
        self._save_entry(
            slug=raw_slug,
            title=title,
            cover_url=cover_url,
            rating=rating,
            date=log_date,
            text=full_text,
            is_spoiler=is_spoiler,
            platform_name=platform_name
        )

    def _fetch_review_details(self, url):
        resp = self._make_request(url)
        if not resp: return None
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Texto Completo (Pode ser Markdown ou HTML raw)
        text_container = soup.select_one('.review-body .card-text, .review-content')
        text = text_container.get_text('\n', strip=True) if text_container else ""
        
        # Spoiler Check
        spoiler = bool(soup.select_one('.spoiler-warning') or soup.select_one('.spoiler-overlay'))
        
        # Plataforma (Geralmente num badge ou ícone)
        # Backloggd costuma por platforma em tags ou icones especificos, é chato de achar no HTML cru
        # Tentativa genérica:
        platform = "PC"
        meta_tags = soup.select('.review-card-metadata a')
        for tag in meta_tags:
            href = tag.get('href', '')
            if '/platform/' in href:
                platform = tag.get_text(strip=True)
                break
                
        return {'text': text, 'spoiler': spoiler, 'platform': platform}

    def _save_entry(self, slug, title, cover_url, rating, date, text, is_spoiler, platform_name):
        # A. Master Game (Stub)
        # Usamos ID negativo baseado no hash do slug para consistência
        temp_id = -(abs(hash(slug)) % 2147483647)
        
        master, _ = MasterGame.objects.get_or_create(
            slug=slug,
            defaults={
                'title': title,
                'igdb_id': temp_id, # Será corrigido pelo enrich_library_task depois
                'cover_url': cover_url,
                'status': 0
            }
        )

        # B. Platform
        plat_slug = slugify(platform_name)
        platform, _ = Platform.objects.get_or_create(
            slug=plat_slug, defaults={'name': platform_name}
        )
        
        pg, _ = PlatformGame.objects.get_or_create(
            master_game=master, platform=platform,
            defaults={'external_id': f"bl_{slug}_{plat_slug}", 'external_title': title}
        )

        # C. User Library Entry
        # Aqui assumimos que se o usuário tem log, ele tem o jogo.
        # Atualizamos o status para 'completed' se tiver rating ou texto, senão 'playing'
        status = 'completed' if (rating or text) else 'playing'
        
        entry, created = UserLibraryEntry.objects.get_or_create(
            user=self.user, platform_game=pg,
            defaults={'status': status}
        )
        
        # Atualiza rating na library apenas se for o log mais recente
        if rating and (not entry.last_played or (date and entry.last_played.date() < date)):
            entry.rating = rating
            entry.status = status
            entry.save()

        # D. Review (A Lógica "Ghost Rider")
        # Se tem texto ou rating, salvamos como Review.
        # Usamos tags para criar uma "impressão digital" dessa review específica
        if text or rating:
            # Verifica se já existe uma review desse usuário, desse jogo, nessa data
            # Como Review não tem campo 'date', usamos created_at filter
            
            # Sanitiza texto
            safe_text = nh3.clean(text) if text else ""
            
            # Tenta encontrar duplicata exata
            exists = Review.objects.filter(
                user=self.user,
                library_entry=entry,
                created_at__date=date, # Comparação por dia
                text=safe_text
            ).exists()

            if not exists:
                review = Review.objects.create(
                    user=self.user,
                    library_entry=entry,
                    text=safe_text,
                    rating=rating,
                    contains_spoilers=is_spoiler,
                    language='pt-br', # Default
                    is_replay=False # Poderíamos inferir se já existisse outra review
                )
                
                # HACK: Forçar a data de criação (Django ignora auto_now_add no create)
                if date:
                    Review.objects.filter(id=review.id).update(created_at=date)
                    self.stdout.write(f"    💾 Review salva: {date} (ID: {review.id})")
            else:
                self.stdout.write(f"    ⏭️ Review duplicada ignorada.")

    def _make_request(self, url):
        try:
            resp = self.scraper.get(url, timeout=30)
            if resp.status_code == 429:
                self.stdout.write(self.style.WARNING("⏳ Rate Limit (429). Dormindo 60s..."))
                time.sleep(60)
                return self._make_request(url)
            if resp.status_code != 200:
                self.stdout.write(self.style.ERROR(f"Erro {resp.status_code} em {url}"))
                return None
            return resp
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erro conexão: {e}"))
            return None
