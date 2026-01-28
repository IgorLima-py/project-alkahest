import requests
from django.core.cache import cache
from decouple import config

def get_igdb_token():
    token = cache.get('igdb_access_token')
    if not token:
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
                cache.set('igdb_access_token', token, timeout=expires_in - 60)
            else:
                return None
        except Exception as e:
            print(f"ERRO DE CONEXÃO IGDB: {e}")
            return None
    return token