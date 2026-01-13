import requests
import time
import re
from django.core.management.base import BaseCommand
from vault.models import MasterGame, PlatformGame
from decouple import config

class Command(BaseCommand):
    help = 'Busca metadados no IGDB via SteamID (Prioridade) ou Nome (Fallback)'

    def handle(self, *args, **kwargs):
        CLIENT_ID = config('TWITCH_CLIENT_ID')
        CLIENT_SECRET = config('TWITCH_CLIENT_SECRET')

        # 1. Autenticação
        self.stdout.write('Autenticando no IGDB...')
        try:
            auth_response = requests.post('https://id.twitch.tv/oauth2/token', params={
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'grant_type': 'client_credentials'
            })
            access_token = auth_response.json().get('access_token')
            if not access_token: raise Exception("Sem token")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro auth: {e}'))
            return

        headers = {'Client-ID': CLIENT_ID, 'Authorization': f'Bearer {access_token}'}

        # 2. Selecionar jogos SEM capa
        # Vamos olhar para TODOS os MasterGames sem capa agora
        games_without_cover = MasterGame.objects.filter(cover_url__isnull=True)
        total = games_without_cover.count()
        
        self.stdout.write(f'Iniciando busca para {total} jogos sem capa...')

        for index, master in enumerate(games_without_cover):
            time.sleep(0.25) # Respeita o limite da API
            
            match_found = None
            
            # --- TENTATIVA 1: Via Steam ID (Se tiver) ---
            # Verifica se esse MasterGame tem algum PlatformGame da Steam ligado a ele
            steam_pg = master.platforms.filter(platform__slug='steam').first()
            
            if steam_pg:
                steam_id = steam_pg.external_id
                query = f'fields name, cover.url, id; where external_games.uid = "{steam_id}" & external_games.category = 1; limit 1;'
                try:
                    res = requests.post('https://api.igdb.com/v4/games', headers=headers, data=query).json()
                    if res: match_found = res[0]
                except: pass

            # --- TENTATIVA 2: Via Nome (Fallback para RetroAchievements) ---
            if not match_found:
                # Limpa o nome (tira parênteses de console ex: "Mario (SNES)" vira "Mario")
                clean_title = re.sub(r'\s*\(.*?\)', '', master.title).strip()
                clean_title = clean_title.replace('"', '') # Tira aspas pra não quebrar a query
                
                self.stdout.write(f'   Tentando por nome: "{clean_title}"...')
                
                # Busca por nome exato ou aproximado
                query = f'search "{clean_title}"; fields name, cover.url, id; limit 1;'
                try:
                    res = requests.post('https://api.igdb.com/v4/games', headers=headers, data=query).json()
                    if res: match_found = res[0]
                except: pass

            # --- PROCESSAR O RESULTADO ---
            if match_found:
                new_igdb_id = int(match_found['id'])
                url_raw = match_found.get('cover', {}).get('url', '')
                cover_url = f"https:{url_raw}".replace('t_thumb', 't_cover_big') if url_raw else None
                
                self.stdout.write(self.style.SUCCESS(f'[{index+1}/{total}] ACHOU! {master.title} -> {match_found["name"]}'))

                # MERGE: Verifica se já existe outro jogo com esse ID real
                existing_master = MasterGame.objects.filter(igdb_id=new_igdb_id).first()

                if existing_master and existing_master != master:
                    self.stdout.write(self.style.WARNING(f'      -> MERGE realizado com ID {new_igdb_id}'))
                    # Move os filhos para o oficial
                    for pg in master.platforms.all():
                        pg.master_game = existing_master
                        pg.save()
                    # Se o oficial não tinha capa, põe a nova
                    if not existing_master.cover_url and cover_url:
                        existing_master.cover_url = cover_url
                        existing_master.save()
                    # Apaga o duplicado
                    master.delete()
                else:
                    # Só atualiza
                    master.igdb_id = new_igdb_id
                    master.cover_url = cover_url
                    master.save()
            else:
                self.stdout.write(f'[{index+1}/{total}] ... Nada encontrado para {master.title}')