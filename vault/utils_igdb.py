import requests
import time
from django.core.cache import cache
from decouple import config

def get_igdb_token():
    token = cache.get('igdb_access_token')
    if token:
        return token

    url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': config('TWITCH_CLIENT_ID'),
        'client_secret': config('TWITCH_CLIENT_SECRET'),
        'grant_type': 'client_credentials'
    }
    
    try:
        response = requests.post(url, params=params)
        response.raise_for_status()
        data = response.json()
        
        token = data['access_token']
        expires_in = data.get('expires_in', 3600)
        # Cache com margem de segurança de 60s
        cache.set('igdb_access_token', token, timeout=expires_in - 60)
        return token
    except Exception as e:
        print(f"[IGDB Auth Error] Falha ao obter token: {e}")
        return None

def igdb_api_request(endpoint, body):
    """
    Wrapper genérico para chamadas à API do IGDB com tratamento de erro e retries.
    """
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

    # Retry simples para oscilações de rede
    for attempt in range(3):
        try:
            response = requests.post(url, headers=headers, data=body)
            
            if response.status_code == 429: # Rate Limit
                print(f"[IGDB Rate Limit] Aguardando 1s... (Tentativa {attempt+1})")
                time.sleep(1)
                continue
                
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"[IGDB Request Error] Endpoint: {endpoint} | Erro: {e}")
            if attempt == 2: return None # Desiste na 3ª tentativa
            time.sleep(1)
            
    return None
