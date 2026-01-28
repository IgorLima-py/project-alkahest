# vault/utils_igdb.py
import requests
from django.core.cache import cache
from decouple import config

# SUA FUNÇÃO ORIGINAL - NÃO MUDOU NADA
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
            response.raise_for_status() # Lança um erro se a requisição falhar (ex: 400, 500)
            data = response.json()
            if 'access_token' in data:
                token = data['access_token']
                expires_in = data.get('expires_in', 3600)
                # Guarda o token no cache por um tempo um pouco menor que a expiração
                cache.set('igdb_access_token', token, timeout=expires_in - 120)
            else:
                print("ERRO: 'access_token' não encontrado na resposta da Twitch.")
                return None
        except requests.exceptions.RequestException as e:
            print(f"ERRO DE CONEXÃO AO OBTER TOKEN IGDB: {e}")
            return None
    return token

# ==========================================
# NOVA FUNÇÃO - O "PESQUISADOR"
# ==========================================
def get_top_games_with_stores(limit=100, offset=0):
    """
    Busca os jogos mais populares no IGDB e retorna seus dados, incluindo os IDs das lojas.
    """
    token = get_igdb_token()
    if not token:
        print("ERRO: Não foi possível obter o token de acesso do IGDB.")
        return [] # Retorna uma lista vazia se não houver token

    url = 'https://api.igdb.com/v4/games'
    client_id = config('TWITCH_CLIENT_ID')
    headers = {
        'Client-ID': client_id,
        'Authorization': f'Bearer {token}',
    }
    
    # Esta é a "linguagem" do IGDB para pedir os dados que queremos
    query = f"""
        fields 
            name, 
            cover.url, 
            summary, 
            external_games.category, 
            external_games.uid;
        sort popularity desc;
        where category = (0, 8, 9);
        limit {limit};
        offset {offset};
    """
    
    try:
        response = requests.post(url, headers=headers, data=query.encode('utf-8'))
        response.raise_for_status() # Lança erro se a resposta não for 200 OK
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"ERRO AO BUSCAR JOGOS NO IGDB: {e}")
        return [] # Retorna uma lista vazia em caso de erro