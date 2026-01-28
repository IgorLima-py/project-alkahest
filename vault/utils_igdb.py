# vault/utils_igdb.py
import logging
import time
import requests
from decouple import config
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# Configurações Globais
BASE_URL = "https://api.igdb.com/v4"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
CLIENT_ID = config('TWITCH_CLIENT_ID')
CLIENT_SECRET = config('TWITCH_CLIENT_SECRET')

# Sessão persistente (Melhora performance SSL em 3x)
session = requests.Session()
retries = Retry(total=3, backoff_factor=1, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

class IGDBError(Exception):
    pass

def get_igdb_token():
    token = cache.get('igdb_access_token')
    if token:
        return token

    logger.info("Solicitando novo token IGDB...")
    try:
        res = session.post(TOKEN_URL, params={
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'client_credentials'
        }, timeout=10)
        res.raise_for_status()
        data = res.json()
        token = data['access_token']
        # Cache com buffer de 60s
        cache.set('igdb_access_token', token, timeout=data['expires_in'] - 60)
        return token
    except Exception as e:
        logger.critical(f"Falha fatal na auth IGDB: {e}")
        return None

# Decorator de Retry para Rate Limit (429) e Erros de Rede
@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.RequestException, IGDBError))
)
def igdb_api_request(endpoint, body):
    token = get_igdb_token()
    if not token:
        raise IGDBError("Sem token de autenticação")

    headers = {
        'Client-ID': CLIENT_ID,
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }

    # Pausa preventiva de segurança (Evita burst que bane IP)
    time.sleep(0.25) 

    response = session.post(f"{BASE_URL}/{endpoint}", headers=headers, data=body, timeout=15)

    if response.status_code == 429:
        logger.warning("Rate Limit atingido. O Tenacity vai tentar de novo...")
        raise requests.exceptions.RequestException("Rate Limit 429")
    
    if response.status_code != 200:
        logger.error(f"Erro IGDB {response.status_code}: {response.text}")
        response.raise_for_status()

    return response.json()
