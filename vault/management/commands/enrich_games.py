import requests
import time
from django.core.management.base import BaseCommand
from vault.models import PlatformGame, MasterGame
from decouple import config

class Command(BaseCommand):
    help = 'Busca metadados no IGDB usando o ID DA STEAM (Muito mais preciso)'

    def handle(self, *args, **kwargs):
        CLIENT_ID = config('TWITCH_CLIENT_ID')
        CLIENT_SECRET = config('TWITCH_CLIENT_SECRET')

        # 1. Autenticação
        self.stdout.write('Autenticando no IGDB...')
        auth_url = 'https://id.twitch.tv/oauth2/token'
        try:
            auth_response = requests.post(auth_url, params={
                'client_id': CLIENT_ID,
                'client_secret': CLIENT_SECRET,
                'grant_type': 'client_credentials'
            })
            access_token = auth_response.json().get('access_token')
            if not access_token:
                raise Exception("Falha ao pegar token")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro auth: {e}'))
            return

        headers = {
            'Client-ID': CLIENT_ID,
            'Authorization': f'Bearer {access_token}',
        }

        # 2. Filtrar apenas jogos da Steam que ainda não têm capa no MasterGame
        # Estamos indo via PlatformGame porque é lá que mora o ID da Steam (external_id)
        games_to_check = PlatformGame.objects.filter(
            platform__slug='steam', 
            master_game__cover_url__isnull=True
        ).select_related('master_game')

        total = games_to_check.count()
        self.stdout.write(f'Tentando parear {total} jogos via Steam ID...')

        for index, p_game in enumerate(games_to_check):
            steam_id = p_game.external_id
            master = p_game.master_game
            
            # Pausa para rate limit
            time.sleep(0.25)
            
            # --- A Query Mágica ---
            # external_games.uid = O ID na loja (Steam ID)
            # external_games.category = 1 (1 é o código da Steam no IGDB)
            query = f'fields name, cover.url, id; where external_games.uid = "{steam_id}" & external_games.category = 1; limit 1;'
            
            try:
                response = requests.post('https://api.igdb.com/v4/games', headers=headers, data=query)
                results = response.json()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Erro request: {e}'))
                continue

            if results:
                match = results[0]
                new_igdb_id = int(match['id'])
                
                # Tratamento da URL da capa
                url_raw = match.get('cover', {}).get('url', '')
                cover_url = f"https:{url_raw}".replace('t_thumb', 't_cover_big') if url_raw else None
                
                self.stdout.write(f'[{index+1}/{total}] MATCH! SteamID {steam_id} -> IGDB {match["name"]}')

                # --- MERGE / UPDATE ---
                # Verifica se já existe um MasterGame com esse IGDB ID
                existing_master = MasterGame.objects.filter(igdb_id=new_igdb_id).first()

                if existing_master and existing_master != master:
                    # Caso de Merge: Já temos esse jogo no banco vindo de outra fonte ou importação anterior
                    self.stdout.write(self.style.WARNING(f'   -> MERGE: Unindo "{master.title}" com "{existing_master.title}"'))
                    p_game.master_game = existing_master
                    p_game.save()
                    master.delete() # Remove o temporário sem capa
                    
                    # Se o original não tinha capa, poe agora
                    if not existing_master.cover_url and cover_url:
                        existing_master.cover_url = cover_url
                        existing_master.save()

                else:
                    # Caso simples: Só atualizar o MasterGame atual
                    master.igdb_id = new_igdb_id
                    master.title = match['name'] # Atualiza para o nome oficial limpo do IGDB
                    master.cover_url = cover_url
                    master.save()

            else:
                # Se não achar pelo ID, aí sim paciência. 
                # Geralmente são Test Servers ou Softwares que o IGDB ignora.
                self.stdout.write(f'[{index+1}/{total}] ... Sem match para SteamID {steam_id} ({master.title})')

        self.stdout.write(self.style.SUCCESS('Enriquecimento via ID concluído!'))