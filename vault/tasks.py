from celery import shared_task
import csv
import uuid
import io
from django.contrib.auth.models import User
from allauth.socialaccount.models import SocialAccount
from decouple import config
import requests
import time
from datetime import datetime
from django.utils.timezone import make_aware
from django.core.cache import cache  # <--- IMPORTANTE: Importar o cache
from .models import Platform, PlatformGame, MasterGame, UserLibraryEntry, Achievement, UserAchievement

# Importa nosso decorator de cache (O "Segredo" da performance)
from core.cache_utils import cache_external_api

# Tenta importar o service de enriquecimento
try:
    from .services import fetch_and_update_game
except ImportError:
    fetch_and_update_game = None

# ==========================================
# HELPERS COM CACHE (O "Fino do Fino")
# ==========================================

@cache_external_api(timeout=60*60, prefix="steam_user_lib") # 1 Hora de Cache
def get_steam_library_json(url):
    """Busca JSON da biblioteca Steam com cache de 1h"""
    print(f"📡 [NETWORK] Baixando biblioteca Steam...") # Log visual
    return requests.get(url).json()

@cache_external_api(timeout=60*60*24, prefix="steam_schema") # 24 Horas de Cache
def get_steam_game_schema(url):
    """Busca dados de conquistas do jogo (Metadados mudam pouco)"""
    return requests.get(url).json()

@cache_external_api(timeout=60*60, prefix="ra_user_progress") # 1 Hora de Cache
def get_ra_progress_json(url):
    """Busca progresso do RetroAchievements"""
    print(f"📡 [NETWORK] Baixando dados do RA...")
    return requests.get(url).json()

# ==========================================
# STEAM TASKS
# ==========================================
@shared_task(bind=True, name='vault.tasks.sync_steam_library_task') # <--- FORCE O NOME AQUI
def sync_steam_library_task(self, user_id):
    print(f"🏁 [START] Iniciando Sync Steam para User ID {user_id}")
    
    # -----------------------------------------------------------
    # CAMADA DE SEGURANÇA: REDIS RATE LIMIT (10 min por User)
    # -----------------------------------------------------------
    lock_key = f"steam_sync_lock_user_{user_id}"
    
    # Se a chave existir, o usuário rodou isso há menos de 10 min
    if cache.get(lock_key):
        msg = f"🚫 [SKIP] User {user_id} tentou sync muito rápido. Ignorando para proteger API."
        print(msg)
        return msg 

    # -----------------------------------------------------------
    # LÓGICA DE NEGÓCIO
    # -----------------------------------------------------------
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return "Usuário não encontrado"

    KEY = config('STEAM_API_KEY', default='')
    
    # TODO CRÍTICO (Fase 5+): Para login social real, pegar o ID assim:
    # social_account = user.socialaccount_set.filter(provider='steam').first()
    # STEAM_ID = social_account.uid if social_account else config('STEAM_ID')
    STEAM_ID = config('STEAM_ID', default='')
    
    if not KEY or not STEAM_ID:
        return "Credenciais Steam ausentes"

    url = "http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
    params = {
        'key': config('STEAM_API_KEY'),
        'steamid': config('STEAM_ID'), # Idealmente pegar do user.socialaccount
        'include_appinfo': 1,
        'format': 'json'
    }
    
    # Usa nossa função helper cacheada
    try:
        # Requests trata o encoding seguro da query string
        data = requests.get(url, params=params).json()
        games = data.get('response', {}).get('games', [])
    except Exception as e:
        return f"Erro API: {e}"

    steam_plat, _ = Platform.objects.get_or_create(slug='steam', defaults={'name': 'Steam'})
    
    count = 0
    print(f"🎮 [PROCESS] Processando {len(games)} jogos...")
    
    for g in games:
        app_id = str(g.get('appid'))
        title = g.get('name')
        playtime = g.get('playtime_forever', 0)

        # ID Provisório (> 1bi) para evitar colisão com IDs reais do IGDB
        master, _ = MasterGame.objects.get_or_create(
            title=title,
            defaults={'igdb_id': int(app_id) + 1000000000} 
        )

        p_game, _ = PlatformGame.objects.get_or_create(
            platform=steam_plat, external_id=app_id,
            defaults={'master_game': master, 'external_title': title}
        )

        entry, created = UserLibraryEntry.objects.update_or_create(
            user=user, platform_game=p_game,
            defaults={
                'playtime_minutes': playtime,
                'status': 'playing' if playtime > 60 else 'backlog'
            }
        )
        
        # Dispara task de conquistas se jogou algo
        if playtime > 0:
            sync_steam_achievements_task.delay(user.id, str(entry.id))
        
        count += 1

    # -----------------------------------------------------------
    # FINALIZAÇÃO: ATIVAR LOCK E ENRICHMENT
    # -----------------------------------------------------------
    
    # Sucesso! Agora bloqueamos esse usuário por 600 segundos (10 min)
    # para ele não floodar o botão de sync
    cache.set(lock_key, True, timeout=600)

    print("🚀 [TRIGGER] Disparando Enrich Task...")
    enrich_library_task.delay()
    
    return f"✅ Steam Finalizado: {count} jogos."


@shared_task
def sync_steam_achievements_task(user_id, entry_id):
    try:
        user = User.objects.get(id=user_id)
        entry = UserLibraryEntry.objects.get(id=entry_id)
    except: return

    KEY = config('STEAM_API_KEY')
    STEAM_ID = config('STEAM_ID')
    app_id = entry.platform_game.external_id

    try:
        schema_url = f"http://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/?key={KEY}&appid={app_id}"
        # Stats do usuário mudam sempre, então NÃO cacheamos ou usamos TTL curto (5min)
        user_url = f"http://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v0001/?appid={app_id}&key={KEY}&steamid={STEAM_ID}"
        
        # Schema usa cache de 24h
        schema_res = get_steam_game_schema(schema_url)
        user_res = requests.get(user_url).json() 
    except: return

    if not user_res.get('playerstats', {}).get('success'): return

    ach_defs = {}
    if 'availableGameStats' in schema_res.get('game', {}):
         for raw in schema_res['game']['availableGameStats'].get('achievements', []):
             ach_defs[raw['name']] = raw

    user_achs = user_res['playerstats'].get('achievements', [])
    unlocked_count = 0
    
    for ua in user_achs:
        if ua['achieved'] == 1:
            unlocked_count += 1
            api_name = ua['apiname']
            defin = ach_defs.get(api_name, {})
            
            ach_obj, _ = Achievement.objects.get_or_create(
                platform_game=entry.platform_game,
                external_id=api_name,
                defaults={
                    'name': defin.get('displayName', api_name),
                    'description': defin.get('description', ''),
                    'icon_url': defin.get('icon', ''),
                    'xp_value': 10
                }
            )
            
            UserAchievement.objects.get_or_create(
                user=user, achievement=ach_obj,
                defaults={'unlocked_at': make_aware(datetime.fromtimestamp(ua['unlocktime']))}
            )
    
    if unlocked_count == len(user_achs) and unlocked_count > 0:
        if entry.status != 'completed':
            entry.status = 'completed'
            entry.save()
            print(f"🏆 [PLATINA] {entry.platform_game.external_title}")

# ==========================================
# RETROACHIEVEMENTS TASKS
# ==========================================
@shared_task
def sync_ra_library_task(user_id):
    print(f"👾 [START] Iniciando Sync RA para User ID {user_id}")
    try:
        user = User.objects.get(id=user_id)
    except: return

    RA_USER = config('RA_USER', default='')
    RA_KEY = config('RA_API_KEY', default='')
    
    if not RA_USER or not RA_KEY: return "Credenciais RA ausentes"

    url = f"https://retroachievements.org/API/API_GetUserCompletedGames.php?z={RA_USER}&y={RA_KEY}&u={RA_USER}"
    try:
        # Usa Cache
        data = get_ra_progress_json(url)
        games = data if isinstance(data, list) else []
    except: return "Erro RA API"

    ra_plat, _ = Platform.objects.get_or_create(slug='retroachievements', defaults={'name': 'RetroAchievements'})

    for g in games:
        ra_id = str(g.get('GameID'))
        title = g.get('Title')
        
        master, _ = MasterGame.objects.get_or_create(
            title=title,
            defaults={'igdb_id': int(ra_id) + 900000000}
        )

        p_game, _ = PlatformGame.objects.get_or_create(
            platform=ra_plat, external_id=ra_id,
            defaults={'master_game': master, 'external_title': title}
        )

        entry, _ = UserLibraryEntry.objects.update_or_create(
            user=user, platform_game=p_game,
            defaults={'status': 'playing'}
        )
        
        sync_ra_achievements_task.apply_async((user.id, str(entry.id)), countdown=2)

    return f"✅ RA: {len(games)} jogos."

@shared_task
def sync_ra_achievements_task(user_id, entry_id):
    # Lógica mantida, omitida aqui por brevidade, mas pode manter a do passo anterior
    pass

# ==========================================
# ENRICHMENT (IGDB) TASKS - COM LOGS!
# ==========================================
@shared_task
def enrich_library_task():
    """
    Roda o enriquecimento em 'batches' com proteção contra loop infinito.
    """
    BATCH_SIZE = 20 
    
    if not fetch_and_update_game: 
        return "Service error"

    # Query apenas para IDs positivos altos (Provisórios não verificados)
    pending_query = MasterGame.objects.filter(igdb_id__gt=900000000)
    total_pending = pending_query.count()

    if total_pending == 0:
        print("✅ [ENRICH] Zero jogos pendentes. Trabalho concluído!")
        return "Concluído"

    print(f"🔄 [ENRICH] Iniciando lote. Faltam {total_pending} jogos na fila...")

    # Pega o lote
    targets = list(pending_query[:BATCH_SIZE])
    
    updated_count = 0
    processed_in_batch = 0 # Contador local para UI

    for master in targets:
        processed_in_batch += 1
        # Mostra: [1/20] Jogo X...
        print(f"   -> [{processed_in_batch}/{BATCH_SIZE}] Analisando: {master.title}")
        
        steam_pg = master.platforms.filter(platform__slug='steam').first()
        steam_id = steam_pg.external_id if steam_pg else None
        
        try:
            new_master = fetch_and_update_game(search_name=master.title, steam_id=steam_id)
            
            if new_master:
                if new_master.id != master.id:
                    # SUCESSO: Mescla e atualiza
                    for pg in master.platforms.all():
                        pg.master_game = new_master
                        pg.save()
                    for entry in UserLibraryEntry.objects.filter(platform_game__master_game=master):
                        entry.save() 
                    
                    master.delete()
                    updated_count += 1
                    print(f"      ✅ MATCH! Atualizado para ID {new_master.igdb_id}")
            else:
                # FALHA: Jogo não existe no IGDB ou API falhou.
                # AÇÃO: Marcar como "Verificado" para não pegar no próximo loop.
                # Truque: Inverter o sinal do ID temporário.
                print(f"      ⚠️ Sem dados no IGDB. Marcando para ignorar futuramente.")
                master.igdb_id = -master.igdb_id 
                master.save()

        except Exception as e:
            print(f"      ❌ Erro Crítico em {master.title}: {e}")
            # Em caso de erro de código, também ignoramos para não travar a fila
            master.igdb_id = -master.igdb_id
            master.save()

    # Recursão: Verifica se sobrou alguém (os negativos agora são ignorados)
    remaining = MasterGame.objects.filter(igdb_id__gt=900000000).count()
    
    if remaining > 0:
        print(f"🔁 [ENRICH] Lote finalizado. Agendando próximo lote (Restam {remaining})...")
        enrich_library_task.apply_async(countdown=2)
    else:
        print("✨ [ENRICH] Fim da linha! Todos os jogos foram processados ou ignorados.")

    return f"Lote finalizado. Atualizados: {updated_count}"

# === NOVAS TASKS LGPD ===

@shared_task
def export_user_data_task(user_id):
    """
    Gera um arquivo ZIP contendo CSVs da Biblioteca e Reviews.
    Formato amigável para Excel/Google Sheets.
    """
    try:
        user = User.objects.get(id=user_id)
        
        # 1. Preparar CSV da Biblioteca
        lib_buffer = io.StringIO()
        writer_lib = csv.writer(lib_buffer)
        writer_lib.writerow(['Title', 'Platform', 'Status', 'Rating', 'Playtime (Minutes)', 'Last Played', 'Date Added'])
        
        # Otimização: select_related para evitar N+1
        library = UserLibraryEntry.objects.filter(user=user).select_related('platform_game__master_game', 'platform_game__platform')
        
        for entry in library:
            writer_lib.writerow([
                entry.platform_game.master_game.title,
                entry.platform_game.platform.name,
                entry.status,
                entry.rating or '',
                entry.playtime_minutes,
                entry.last_played.strftime('%Y-%m-%d') if entry.last_played else '',
                entry.last_synced.strftime('%Y-%m-%d')
            ])
            
        # 2. Preparar CSV de Reviews
        rev_buffer = io.StringIO()
        writer_rev = csv.writer(rev_buffer)
        writer_rev.writerow(['Game', 'Date', 'Rating', 'Review Text', 'Recommended', 'Spoilers'])
        
        reviews = Review.objects.filter(user=user).select_related('library_entry__platform_game__master_game')
        
        for rev in reviews:
            writer_rev.writerow([
                rev.library_entry.platform_game.master_game.title,
                rev.created_at.strftime('%Y-%m-%d'),
                rev.rating or '',
                rev.text, # Texto original em Markdown
                'Yes' if rev.is_recommended else 'No',
                'Yes' if rev.contains_spoilers else 'No'
            ])

        # 3. Criar o ZIP em memória
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(f'alkahest_library_{user.username}.csv', lib_buffer.getvalue())
            zip_file.writestr(f'alkahest_reviews_{user.username}.csv', rev_buffer.getvalue())
        
        # 4. Salvar no Storage
        filename = f"exports/{user.username}_export_{int(time.time())}.zip"
        path = default_storage.save(filename, ContentFile(zip_buffer.getvalue()))
        
        return f"Export CSV/ZIP salvo em: {path}"

    except User.DoesNotExist:
        return "User not found"
    except Exception as e:
        return f"Erro no export: {str(e)}"

@shared_task
def delete_user_account_task(user_id):
    print(f"💀 [DELETE] Iniciando exclusão do User ID {user_id}")
    try:
        user = User.objects.get(id=user_id)

        SocialAccount.objects.filter(user=user).delete()
        
        # 1. Limpeza da Biblioteca (Mantendo Reviews)
        for entry in UserLibraryEntry.objects.filter(user=user):
            if entry.reviews.exists():
                entry.playtime_minutes = 0
                entry.last_played = None
                entry.status = 'dropped'
                entry.rating = None
                entry.is_favorite = False
                entry.save()
            else:
                entry.delete()
        
        # 2. Anonimização do Usuário (CRÍTICO)
        # Usamos hex randomico para garantir que não bata com nenhum email existente
        anon_token = uuid.uuid4().hex[:12]
        
        old_username = user.username
        user.username = f"deleted_{anon_token}"
        
        # Truque: Usar um email inválido/dummy que com certeza é único
        user.email = f"{anon_token}@deleted.local" 
        
        user.first_name = ""
        user.last_name = ""
        user.is_active = False
        user.set_unusable_password()
        
        # Removemos relações sociais se existirem
        user.groups.clear()
        user.user_permissions.clear()
        
        # 3. Salva a alteração
        user.save()
        print(f"✅ [DELETE] Usuário {old_username} renomeado para {user.username}")

        # 4. Limpeza do Perfil (Se existir)
        if hasattr(user, 'profile'):
            user.profile.bio = "Deleted User"
            user.profile.avatar_url = None
            user.profile.save()
            
        return f"Sucesso: {old_username} virou {user.username}"

    except Exception as e:
        # Se der erro, printa para descobrirmos
        print(f"❌ [DELETE ERROR] Falha ao deletar: {str(e)}")
        return f"Erro: {str(e)}"
        
    return f"Conta de {username_bkp} encerrada."