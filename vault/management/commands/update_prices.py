import requests
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from vault.models import GameStoreLink, PriceHistory, Store

class Command(BaseCommand):
    help = 'Coleta preços atuais das lojas (Steam/GOG) e atualiza o histórico.'

    def add_arguments(self, parser):
        parser.add_argument('--store', type=str, default='all', help='steam, gog, ou all')
        parser.add_argument('--force', action='store_true', help='Força atualização mesmo se tiver sido checado recentemente')

    def handle(self, *args, **options):
        target_store = options['store']
        force = options['force']
        
        self.stdout.write(self.style.MIGRATE_HEADING(f"--- INICIANDO COLETA DE PREÇOS ({target_store.upper()}) ---"))

        if target_store in ['steam', 'all']:
            self._update_steam(force)
        
        if target_store in ['gog', 'all']:
            self._update_gog(force)

    # ==========================
    # ENGINE: STEAM
    # API: http://store.steampowered.com/api/appdetails?appids=...&filters=price_overview
    # Limite: ~200 requests/5min. Suporta múltiplos IDs por call.
    # ==========================
    def _update_steam(self, force):
        store = Store.objects.filter(slug='steam').first()
        if not store: return

        # 1. Seleciona Links da Steam
        links = GameStoreLink.objects.filter(store=store)
        if not force:
            # Pega apenas os que não foram atualizados nas últimas 12h
            cutoff = timezone.now() - timezone.timedelta(hours=12)
            links = links.filter(last_checked_at__lte=cutoff) | links.filter(last_checked_at__isnull=True)
        
        total = links.count()
        if total == 0:
            self.stdout.write("Steam: Nenhum jogo pendente de atualização.")
            return

        self.stdout.write(f"Steam: Atualizando {total} jogos...")

        # 2. Processamento em Batches (Steam aceita múltiplos IDs, mas é arriscado. Vamos de 1 em 1 seguro por enquanto)
        # Nota: Para escalar para 10k jogos, mudaremos para requests com múltiplos IDs no futuro.
        
        processed = 0
        errors = 0
        
        for link in links:
            app_id = link.external_id
            url = f"http://store.steampowered.com/api/appdetails?appids={app_id}&filters=price_overview&cc=br" # CC=BR força Real
            
            try:
                # Rate Limiting manual (segurança)
                time.sleep(1.5) 
                
                resp = requests.get(url, timeout=10)
                data = resp.json()
                
                # A resposta da Steam é chata: { "app_id": { "success": true, "data": {...} } }
                if data and str(app_id) in data:
                    game_data = data[str(app_id)]
                    
                    if game_data.get('success') and 'price_overview' in game_data.get('data', {}):
                        price_data = game_data['data']['price_overview']
                        
                        # Preços vêm em centavos (1999 = R$ 19,99)
                        price_final = price_data['final'] / 100
                        price_regular = price_data.get('initial', price_data['final']) / 100
                        discount = price_data.get('discount_percent', 0) > 0
                        currency = price_data.get('currency', 'BRL')

                        # Salva Histórico
                        PriceHistory.objects.create(
                            link=link,
                            price_regular=price_regular,
                            price_final=price_final,
                            currency=currency,
                            is_on_sale=discount
                        )
                        
                        # Atualiza timestamp do link
                        link.last_checked_at = timezone.now()
                        link.save()
                        
                        print(f" -> [Steam] {link.master_game.title}: R$ {price_final} (Salvo)")
                    else:
                        # Jogo Grátis ou Delisted
                        # print(f" -> [Steam] {link.master_game.title}: Sem preço (Grátis?)")
                        link.last_checked_at = timezone.now()
                        link.save()
                
                processed += 1
                
            except Exception as e:
                print(f"Erro Steam ID {app_id}: {e}")
                errors += 1

        self.stdout.write(self.style.SUCCESS(f"Steam Finalizada: {processed} ok, {errors} erros."))

    # ==========================
    # ENGINE: GOG
    # API: https://api.gog.com/products/{id}/prices?countryCode=BR
    # ==========================
    def _update_gog(self, force):
        store = Store.objects.filter(slug='gog').first()
        if not store: return
        
        links = GameStoreLink.objects.filter(store=store)
        if not force:
            cutoff = timezone.now() - timezone.timedelta(hours=12)
            links = links.filter(last_checked_at__lte=cutoff) | links.filter(last_checked_at__isnull=True)
            
        total = links.count()
        if total == 0: return

        self.stdout.write(f"GOG: Atualizando {total} jogos...")
        
        for link in links:
            gog_id = link.external_id
            url = f"https://api.gog.com/products/{gog_id}/prices?countryCode=BR"
            
            try:
                time.sleep(1) # GOG é mais tranquila, mas respeitamos
                resp = requests.get(url, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    # Estrutura GOG: { "_embedded": { "items": [ { "currency": "BRL", "basePrice": "1000", "finalPrice": "500" } ] } }
                    
                    items = data.get('_embedded', {}).get('items', [])
                    if items:
                        price_item = items[0] # Pega o primeiro (BRL)
                        
                        # GOG também usa centavos na string "1999" -> 19.99
                        p_final = float(price_item['finalPrice'].split(' ')[0]) / 100
                        p_base = float(price_item['basePrice'].split(' ')[0]) / 100
                        
                        PriceHistory.objects.create(
                            link=link,
                            price_regular=p_base,
                            price_final=p_final,
                            currency=price_item['currency'],
                            is_on_sale=(p_final < p_base)
                        )
                        link.last_checked_at = timezone.now()
                        link.save()
                        print(f" -> [GOG] {link.master_game.title}: R$ {p_final}")
                    
            except Exception as e:
                print(f"Erro GOG ID {gog_id}: {e}")
