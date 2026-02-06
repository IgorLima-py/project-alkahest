# vault/tasks.py
from celery import shared_task
import csv
import uuid
import io
import time
import requests
from datetime import datetime
from decouple import config

from django.contrib.auth.models import User
from allauth.socialaccount.models import SocialAccount
from django.utils.timezone import make_aware
from django.core.cache import cache
from django.db.models import Q
from django.db import transaction
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from .models import (
    Platform, PlatformGame, MasterGame, 
    UserLibraryEntry, Achievement, UserAchievement, 
    Review, ProfileImportJob
)

# Importa Services
from .services import BackloggdScraperService
try:
    from .services import fetch_and_update_game
except ImportError:
    fetch_and_update_game = None

# Importa Cache Utils
from core.cache_utils import cache_external_api


# ==========================================
# HELPERS COM CACHE
# ==========================================

@cache_external_api(timeout=60*60, prefix="steam_user_lib") 
def get_steam_library_json(url):
    print(f"📡 [NETWORK] Baixando biblioteca Steam...")
    return requests.get(url).json()

@cache_external_api(timeout=60*60*24, prefix="steam_schema")
def get_steam_game_schema(url):
    return requests.get(url).json()

@cache_external_api(timeout=60*60, prefix="ra_user_progress")
def get_ra_progress_json(url):
    print(f"📡 [NETWORK] Baixando dados do RA...")
    return requests.get(url).json()


# ==========================================
# STEAM TASKS
# ==========================================
@shared_task(bind=True, name='vault.tasks.sync_steam_library_task')
def sync_steam_library_task(self, user_id):
    print(f"🏁 [START] Iniciando Sync Steam para User ID {user_id}")
    lock_key = f"steam_sync_lock_user_{user_id}"
    
    if cache.get(lock_key):
        msg = f"🚫 [SKIP] User {user_id} tentou sync muito rápido."
        print(msg)
        return msg 

    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return "Usuário não encontrado"

    KEY = config('STEAM_API_KEY', default='')
    STEAM_ID = config('STEAM_ID', default='')
    
    if not KEY or not STEAM_ID:
        return "Credenciais Steam ausentes"

    url = "http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/"
    params = {
        'key': KEY,
        'steamid': STEAM_ID,
        'include_appinfo': 1,
        'format': 'json'
    }
    
    try:
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
        
        if playtime > 0:
            sync_steam_achievements_task.delay(user.id, str(entry.id))
        
        count += 1

    cache.set(lock_key, True, timeout=600)
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
        user_url = f"http://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v0001/?appid={app_id}&key={KEY}&steamid={STEAM_ID}"
        
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
    pass


# ==========================================
# ENRICHMENT (IGDB) TASKS
# ==========================================
# ==========================================
# ENRICHMENT (IGDB) TASKS
# ==========================================
@shared_task
def enrich_library_task():
    """
    Pega jogos importados (IDs negativos) ou Provisórios (IDs > 900mi)
    e busca os dados oficiais no IGDB.
    
    BLINDAGEM: 
    1. Prioriza Steam ID.
    2. Usa Cache para ignorar jogos que falharam recentemente (evita loop infinito).
    """
    BATCH_SIZE = 10 
    
    if not fetch_and_update_game: return "Service error"

    # IDs negativos são do Importador Backloggd
    # IDs > 900mi são do Steam/RA importer
    targets = MasterGame.objects.filter(
        Q(igdb_id__gt=900000000) | Q(igdb_id__lt=0)
    )[:BATCH_SIZE]

    if not targets:
        return "Nenhum jogo pendente de enriquecimento."

    print(f"🔄 [ENRICH] Processando lote de {len(targets)} jogos...")
    updated_count = 0
    skipped_count = 0

    for master in targets:
        # --- TRAVA ANTI-LOOP (REDIS) ---
        # Se já tentamos esse ID nas últimas 24h e falhou, pula.
        lock_key = f"ignore_enrich_{master.id}"
        if cache.get(lock_key):
            print(f" ⏩ [SKIP] {master.title} (Já falhou recentemente)")
            skipped_count += 1
            continue
        # -------------------------------

        original_title = master.title
        steam_id = None
        
        # Tenta extrair ID da Steam para busca exata
        try:
            steam_pg = master.platforms.filter(platform__slug='steam').first()
            if steam_pg:
                steam_id = steam_pg.external_id
                print(f" 🔎 [STEAM ID] Usando AppID {steam_id} para: {original_title}")
            else:
                print(f" 🔎 [NOME] Buscando: {original_title}")
        except: pass

        try:
            new_master = fetch_and_update_game(
                search_name=original_title, 
                steam_id=steam_id
            )
            
            if new_master and new_master.id != master.id:
                print(f"    ✅ SUCESSO! Mesclando...")
                
                with transaction.atomic():
                    # Move PlatformGames
                    for pg in master.platforms.all():
                        if not PlatformGame.objects.filter(master_game=new_master, platform=pg.platform).exists():
                            pg.master_game = new_master
                            pg.save()
                        else:
                            # Conflito: deleta duplicata e move library entries
                            official_pg = PlatformGame.objects.get(master_game=new_master, platform=pg.platform)
                            pg.userlibraryentry_set.update(platform_game=official_pg)
                            pg.delete()
                    
                master.delete()
                updated_count += 1
            else:
                print(f"    ⚠️ FALHOU. Marcando para ignorar por 24h.")
                # TRAVA ATIVADA: Não tenta esse ID de novo por 1 dia (86400s)
                cache.set(lock_key, True, timeout=86400)
                
        except Exception as e:
            print(f"    ❌ ERRO: {e}")
            cache.set(lock_key, True, timeout=3600) # Erro de código? Ignora por 1h só.

    # Re-agenda APENAS se houver items que NÃO foram ignorados/processados no lote
    # Se tudo foi "Skipped", o loop para para não fritar a CPU.
    # A task será chamada de novo naturalmente pelo próximo user action ou cron.
    remaining = len(targets) - (updated_count + skipped_count)
    if remaining > 0 or updated_count > 0:
        enrich_library_task.apply_async(countdown=5)

    return f"Lote fim. Atualizados: {updated_count}, Ignorados: {skipped_count}"

# ==========================================
# IMPORTADOR BACKLOGGD (CELERY TASK)
# ==========================================
@shared_task(bind=True)
def run_backloggd_import_task(self, job_id):
    """Task Celery que roda o scraper."""
    job = ProfileImportJob.objects.get(id=job_id)
    service = BackloggdScraperService(job_id)
    
    try:
        service.run()
    except Exception as e:
        job.status = 'failed'
        job.save()
        raise e


# ==========================================
# EXPORT & DELETE TASKS (LGPD)
# ==========================================

@shared_task
def export_user_data_task(user_id):
    try:
        user = User.objects.get(id=user_id)
        
        # 1. Preparar CSV da Biblioteca
        lib_buffer = io.StringIO()
        writer_lib = csv.writer(lib_buffer)
        writer_lib.writerow(['Title', 'Platform', 'Status', 'Rating', 'Playtime (Minutes)', 'Last Played', 'Date Added'])
        
        library = UserLibraryEntry.objects.filter(user=user).select_related('platform_game__master_game', 'platform_game__platform')
        for entry in library:
            writer_lib.writerow([
                entry.platform_game.master_game.title,
                entry.platform_game.platform.name,
                entry.status,
                entry.rating or '',
                entry.playtime_minutes,
                (entry.last_played.strftime('%Y-%m-%d') if entry.last_played else ''),
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
                rev.text,
                'Yes' if rev.is_recommended else 'No',
                'Yes' if rev.contains_spoilers else 'No'
            ])

        # 3. Criar ZIP
        import zipfile
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr(f'alkahest_library_{user.username}.csv', lib_buffer.getvalue())
            zip_file.writestr(f'alkahest_reviews_{user.username}.csv', rev_buffer.getvalue())
        
        filename = f"exports/{user.username}_export_{int(time.time())}.zip"
        path = default_storage.save(filename, ContentFile(zip_buffer.getvalue()))
        return f"Export CSV/ZIP salvo em: {path}"

    except Exception as e:
        return f"Erro no export: {str(e)}"

@shared_task
def delete_user_account_task(user_id):
    print(f"💀 [DELETE] Iniciando exclusão do User ID {user_id}")
    try:
        user = User.objects.get(id=user_id)
        old_username = user.username
        
        SocialAccount.objects.filter(user=user).delete()
        
        # 1. Anonimizar Reviews (LGPD - Direito ao Esquecimento)
        # Em vez de apenas limpar a library, anonimizamos o conteúdo público
        user_reviews = Review.objects.filter(user=user)
        user_reviews.update(
            title="[Conta Excluída]",
            text="[O conteúdo desta análise foi removido a pedido do usuário]",
            text_html="<p><em>[O conteúdo desta análise foi removido a pedido do usuário]</em></p>",
            rating=None,
            is_recommended=None,
            likes_count=0
        )

        # 2. Limpeza da Biblioteca
        for entry in UserLibraryEntry.objects.filter(user=user):
            # Se tem review (agora anonimizado), mantemos o registro mas limpamos dados pessoais
            if entry.reviews.exists():
                entry.playtime_minutes = 0
                entry.last_played = None
                entry.status = 'dropped'
                entry.rating = None
                entry.is_favorite = False
                entry.save()
            else:
                # Se não tem review, pode deletar tudo
                entry.delete()
        
        # Anonimização
        anon_token = uuid.uuid4().hex[:12]
        user.username = f"deleted_{anon_token}"
        user.email = f"{anon_token}@deleted.local" 
        user.first_name = ""
        user.last_name = ""
        user.is_active = False
        user.set_unusable_password()
        
        user.groups.clear()
        user.user_permissions.clear()
        user.save()
        
        if hasattr(user, 'profile'):
            user.profile.bio = "Deleted User"
            user.profile.avatar_url = None
            user.profile.save()
            
        return f"Sucesso: {old_username} virou {user.username}"

    except Exception as e:
        return f"Erro: {str(e)}"
