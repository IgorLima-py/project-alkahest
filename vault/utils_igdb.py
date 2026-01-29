import logging
import time
import requests
from decouple import config
from django.core.cache import cache
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from core.cache_utils import cache_external_api

logger = logging.getLogger(__name__)

BASE_URL = "https://api.igdb.com/v4"
TOKEN_URL = "https://id.twitch.tv/oauth2/token"
CLIENT_ID = config('TWITCH_CLIENT_ID')
CLIENT_SECRET = config('TWITCH_CLIENT_SECRET')

session = requests.Session()
retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
session.mount('https://', HTTPAdapter(max_retries=retries))

class IGDBError(Exception): pass
class IGDBUnauthorizedError(IGDBError): pass

def get_igdb_token(force_refresh=False):
    if not force_refresh:
        token = cache.get('igdb_access_token')
        if token: return token

    logger.info("♻️ Renovando Token IGDB...")
    try:
        res = session.post(TOKEN_URL, params={
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'grant_type': 'client_credentials'
        }, timeout=10)
        res.raise_for_status()
        data = res.json()
        token = data['access_token']
        # Guarda por menos tempo que a validade real para segurança
        cache.set('igdb_access_token', token, timeout=data['expires_in'] - 300)
        return token
    except Exception as e:
        logger.critical(f"❌ Falha fatal auth IGDB: {e}")
        return None

def _make_request(endpoint, body, token):
    headers = {
        'Client-ID': CLIENT_ID,
        'Authorization': f'Bearer {token}',
        'Accept': 'application/json'
    }
    # Rate limit preventivo simples
    time.sleep(0.3)
    response = session.post(f"{BASE_URL}/{endpoint}", headers=headers, data=body, timeout=10)
    
    if response.status_code == 401:
        raise IGDBUnauthorizedError("Token expirado")
    
    response.raise_for_status()
    return response.json()

# Wrapper público com Retry inteligente e Cache de Resposta
@cache_external_api(timeout=60*60*24, prefix="igdb_raw") # Cacheia a resposta da query por 24h
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=5),
    retry=retry_if_exception_type((requests.RequestException, IGDBError))
)
def igdb_api_request(endpoint, body):
    try:
        token = get_igdb_token()
        if not token: raise IGDBError("Sem token")
        return _make_request(endpoint, body, token)
    except IGDBUnauthorizedError:
        logger.warning("⚠️ Token IGDB expirado. Limpando cache e tentando de novo...")
        cache.delete('igdb_access_token')
        # Tenta mais uma vez com token novo
        token = get_igdb_token(force_refresh=True)
        return _make_request(endpoint, body, token)
