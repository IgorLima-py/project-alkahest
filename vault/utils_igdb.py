import requests
from django.core.cache import cache
from decouple import config

def get_igdb_token():
    """
    Obtém um token de acesso da Twitch/IGDB.
    Verifica se já existe um token válido no cache (memória) antes de pedir um novo.
    Isso acelera a busca e evita bloqueios da API.
    """
    # 1. Tenta pegar do cache
    token = cache.get('igdb_access_token')
    
    if not token:
        # 2. Se não tem no cache, pede pra Twitch
        url = 'https://id.twitch.tv/oauth2/token'
        params = {
            'client_id': config('TWITCH_CLIENT_ID'),
            'client_secret': config('TWITCH_CLIENT_SECRET'),
            'grant_type': 'client_credentials'
        }
        
        try:
            response = requests.post(url, params=params)
            data = response.json()
            
            if 'access_token' in data:
                token = data['access_token']
                expires_in = data.get('expires_in', 3600)
                
                # 3. Salva no cache pelo tempo de vida do token (menos 60s de margem)
                cache.set('igdb_access_token', token, timeout=expires_in - 60)
            else:
                print("ERRO AO OBTER TOKEN IGDB:", data)
                return None
                
        except Exception as e:
            print(f"ERRO DE CONEXÃO IGDB: {e}")
            return None
    
    return token