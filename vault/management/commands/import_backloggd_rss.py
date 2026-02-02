import requests
import re
from datetime import datetime
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from django.utils.dateparse import parse_datetime
from vault.models import MasterGame, Platform, PlatformGame, UserLibraryEntry, Review
from vault.services import fetch_and_update_game  # Reusa seu service inteligente

class Command(BaseCommand):
    help = 'Importa Reviews via RSS (Alta Precisão de Datas e Texto)'

    def add_arguments(self, parser):
        parser.add_argument('backloggd_username', type=str, help='Username do Backloggd')
        parser.add_argument('--target_user', type=str, help='Username local no Django (ex: admin)')

    def handle(self, *args, **options):
        bg_user = options['backloggd_username']
        local_user_str = options.get('target_user') or bg_user

        # 1. Busca Usuário Local
        try:
            user = User.objects.get(username=local_user_str)
        except User.DoesNotExist:
            self.stdout.write(self.style.ERROR(
                f"❌ ERRO: O usuário local '{local_user_str}' não existe no seu banco.\n"
                f"   Use o argumento --target_user para apontar para seu usuário real (ex: admin)."
            ))
            return

        rss_url = f"https://backloggd.com/u/{bg_user}/reviews/rss/"
        self.stdout.write(f"📡 Baixando RSS: {rss_url}")

        try:
            resp = requests.get(rss_url, headers={'User-Agent': 'Alkahest/1.0'})
            if resp.status_code != 200:
                self.stdout.write(self.style.ERROR(f"Erro {resp.status_code} ao baixar RSS."))
                return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erro de conexão: {e}"))
            return

        soup = BeautifulSoup(resp.content, 'xml')
        items = soup.find_all('item')
        
        self.stdout.write(f"📄 Encontrados {len(items)} itens no RSS.")

        count_new = 0
        count_skip = 0

        for item in items:
            try:
                self._process_item(item, user)
                count_new += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Falha ao processar item: {e}"))
                count_skip += 1

        self.stdout.write(self.style.SUCCESS(f"\n✅ Importação RSS Finalizada. Novos: {count_new}, Erros: {count_skip}"))

    def _process_item(self, item, user):
        # --- 1. Extração de Dados ---
        raw_title = item.title.text # Ex: "Ghost Rider (2007) - ★★★★½"
        link = item.link.text
        desc = item.description.text # Texto da Review
        pub_date_str = item.pubDate.text # Ex: "Sun, 01 Feb 2026 12:37:14 +0000"
        
        # Namespace do Backloggd para rating
        # BeautifulSoup xml lida com namespaces meio mal as vezes, vamos tentar direto ou via find
        rating_tag = item.find('backloggd:user_rating')
        rating_val = int(rating_tag.text) * 10 if rating_tag else None # Converte 10 -> 100
        
        # Parse Data (Formato RFC 822)
        # Python 3.7+ pode usar %z para timezone
        try:
            review_date = datetime.strptime(pub_date_str, "%a, %d Feb %Y %H:%M:%S %z")
        except ValueError:
            # Fallback para tentar parsing mais flexível se falhar
            review_date = datetime.now().astimezone()

        # --- 2. Limpeza do Título para Match ---
        # Remove " - ★★★★½" e "(ANO)"
        clean_title = raw_title.split(' - ')[0] # Remove rating
        clean_title = re.sub(r'\s*\(\d{4}\)$', '', clean_title) # Remove (2024) do fim
        
        self.stdout.write(f"🔍 Processando: {clean_title} ({review_date})")

        # --- 3. Busca/Cria Jogo (Reusa sua lógica inteligente) ---
        # Primeiro verifica se já temos localmente pelo slug (extraído do link)
        # Link: https://backloggd.com/u/user/review/4092550/ -> Não tem slug fácil
        # Vamos confiar no fetch_and_update_game
        
        master = fetch_and_update_game(search_name=clean_title)
        
        if not master:
            self.stdout.write(self.style.WARNING(f"   ⚠️ Jogo não encontrado no IGDB: {clean_title}"))
            return

        # --- 4. Garante Entrada na Library ---
        # Como é review, assumimos 'completed' ou 'playing'.
        # O RSS não diz a plataforma específica (ex: PS2), então usamos padrão ou existente.
        
        # Tenta achar entry existente
        entry = UserLibraryEntry.objects.filter(
            user=user, 
            platform_game__master_game=master
        ).first()

        if not entry:
            # Se não tem, cria default (PC ou genérico)
            plat, _ = Platform.objects.get_or_create(slug='pc', defaults={'name': 'PC'})
            pg, _ = PlatformGame.objects.get_or_create(
                master_game=master, platform=plat, 
                defaults={'external_id': f"rss_{master.id}", 'external_title': master.title}
            )
            entry = UserLibraryEntry.objects.create(
                user=user, platform_game=pg, status='completed'
            )

        # Atualiza rating da library se for mais recente
        if rating_val and (not entry.last_played or entry.last_played < review_date):
            entry.rating = rating_val
            entry.save()

        # --- 5. Cria/Atualiza Review (Log Journaling) ---
        # AQUI RESOLVEMOS O GHOST RIDER DUPLICADO
        # Usamos a data EXATA do RSS para diferenciar logs
        
        review, created = Review.objects.get_or_create(
            user=user,
            library_entry=entry,
            created_at=review_date, # O pulo do gato: data exata com hora
            defaults={
                'text': desc,
                'rating': rating_val,
                'contains_spoilers': False, # RSS não mostra spoiler flag infelizmente
            }
        )
        
        if created:
            # Força a data correta (django auto_now_add ignora o valor passado no create)
            Review.objects.filter(id=review.id).update(created_at=review_date)
            self.stdout.write(f"   ✅ Review Criada: {review_date.strftime('%H:%M:%S')}")
        else:
            self.stdout.write(f"   ⏭️ Review já existia.")

