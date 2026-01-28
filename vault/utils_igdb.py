import requests
import time
from django.core.cache import cache
from decouple import config

def get_igdb_token():
    # Tenta pegar do cache primeiro
    token = cache.get('igdb_access_token')
    if token:
        return token

    print("--- [DEBUG] Solicitando NOVO Token Twitch ---")
    url = 'https://id.twitch.tv/oauth2/token'
    client_id = config('TWITCH_CLIENT_ID', default='')
    client_secret = config('TWITCH_CLIENT_SECRET', default='')

    if not client_id or not client_secret:
        print("!!! [ERRO FATAL] TWITCH_CLIENT_ID ou SECRET não encontrados no .env !!!")
        return None

    params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'client_credentials'
    }
    
    try:
        response = requests.post(url, params=params)
        print(f"--- [DEBUG] Status Token: {response.status_code}")
        
        if response.status_code != 200:
            print(f"!!! [ERRO TOKEN] Resposta: {response.text}")
            return None

        data = response.json()
        token = data['access_token']
        expires_in = data.get('expires_in', 3600)
        cache.set('igdb_access_token', token, timeout=expires_in - 60)
        return token
    except Exception as e:
        print(f"!!! [ERRO EXCEÇÃO] Falha ao obter token: {e}")
        return None

def igdb_api_request(endpoint, body):
    token = get_igdb_token()
    if not token:
        return None

    client_id = config('TWITCH_CLIENT_ID')
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }
    url = f"https://api.igdb.com/v4/{endpoint}"

    print(f"--- [DEBUG] Request IGDB para: {url} ---")
    # print(f"--- [DEBUG] Query Body: {body}") # Descomente se quiser ver a query exata

    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, data=body)
            
            if response.status_code != 200:
                print(f"!!! [ERRO API] Status: {response.status_code}")
                print(f"!!! [ERRO API] Corpo: {response.text}")
            
            if response.status_code == 429:
                time.sleep(1)
                continue
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"!!! [ERRO REQUEST] Tentativa {attempt+1}: {e}")
            if attempt == 2: return None
            time.sleep(1)
            
    return None
