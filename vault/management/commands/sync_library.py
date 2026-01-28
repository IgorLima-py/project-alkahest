import requests
import time
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware
from django.contrib.auth.models import User
from decouple import config
from vault.models import Platform, PlatformGame, MasterGame, UserLibraryEntry, Achievement, UserAchievement

class Command(BaseCommand):
    help = 'Sincroniza biblioteca (Jogos + Conquistas) de fontes externas (Steam, RA)'

    def add_arguments(self, parser):
        parser.add_argument('--target', type=str, help='steam, ra, ou all')
        parser.add_argument('--user', type=str, help='Username do Django para vincular (default: primeiro superuser)')

    def handle(self, *args, **options):
        target = options['target']
        username = options['user']

        # 1. Identificar Usuário Local
        if username:
            user = User.objects.filter(username=username).first()
        else:
            user = User.objects.filter(is_superuser=True).first()
        
        if not user:
            self.stdout.write(self.style.ERROR("Nenhum usuário encontrado."))
            return

        self.stdout.write(f"Sincronizando biblioteca para: {user.username}")

        # 2. Roteamento
        if target == 'steam' or target == 'all':
            self._sync_steam(user)
        if target == 'ra' or target == 'all':
            self._sync_ra(user)

    # ==========================
    # LÓGICA STEAM
    # ==========================
    def _sync_steam(self, user):
        KEY = config('STEAM_API_KEY', default='')
        STEAM_ID = config('STEAM_ID', default='')
        if not KEY or not STEAM_ID:
            self.stdout.write(self.style.WARNING("Steam: Credenciais ausentes no .env. Pulando."))
            return

        self.stdout.write(self.style.MIGRATE_HEADING("--- INICIANDO STEAM SYNC ---"))
        
        # A. Importar Jogos
        try:
            url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={KEY}&steamid={STEAM_ID}&include_appinfo=1&format=json"
            data = requests.get(url).json()
            games = data.get('response', {}).get('games', [])
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Erro Steam API: {e}"))
            return

        steam_plat, _ = Platform.objects.get_or_create(slug='steam', defaults={'name': 'Steam'})
        
        self.stdout.write(f"Processando {len(games)} jogos da Steam...")
        
        for g in games:
            app_id = str(g.get('appid'))
            title = g.get('name')
            playtime = g.get('playtime_forever', 0)

            # Master Provisório (Será corrigido pelo enrich_library)
            # Usamos um ID negativo temporário ou hash para não colidir com IGDB real
            temp_id = int(app_id) + 1000000000 # Offset gigante
            master, _ = MasterGame.objects.get_or_create(
                title=title,
                defaults={'igdb_id': temp_id} 
            )

            p_game, _ = PlatformGame.objects.get_or_create(
                platform=steam_plat, external_id=app_id,
                defaults={'master_game': master, 'external_title': title}
            )

            entry, _ = UserLibraryEntry.objects.update_or_create(
                user=user, platform_game=p_game,
                defaults={
                    'playtime_minutes': playtime,
                    'status': 'playing' if playtime > 0 else 'backlog'
                }
            )

            # B. Sincronizar Conquistas (Imediato)
            if playtime > 0: # Só busca conquistas se já jogou
                self._fetch_steam_achievements(user, entry, KEY, STEAM_ID)

    def _fetch_steam_achievements(self, user, entry, key, steam_id):
        app_id = entry.platform_game.external_id
        
        # Schema (Definições)
        try:
            schema_res = requests.get(f"http://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/?key={key}&appid={app_id}").json()
            user_res = requests.get(f"http://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v0001/?appid={app_id}&key={key}&steamid={steam_id}").json()
        except: return 

        if not user_res.get('playerstats', {}).get('success'): return

        # Mapeamento Rápido
        ach_defs = {}
        if 'availableGameStats' in schema_res.get('game', {}):
             for raw in schema_res['game']['availableGameStats'].get('achievements', []):
                 ach_defs[raw['name']] = raw

        user_achs = user_res['playerstats'].get('achievements', [])
        if not user_achs: return

        # Bulk Update seria ideal, mas vamos um a um por segurança
        unlocked_count = 0
        for ua in user_achs:
            if ua['achieved'] == 1:
                unlocked_count += 1
                api_name = ua['apiname']
                
                # Pega dados do schema se tiver
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
        
        # Auto-Completion
        if unlocked_count == len(user_achs) and unlocked_count > 0:
            if entry.status != 'completed':
                entry.status = 'completed'
                entry.save()
                self.stdout.write(self.style.SUCCESS(f"   -> {entry.platform_game.master_game.title} PLATINADO!"))


    # ==========================
    # LÓGICA RETROACHIEVEMENTS
    # ==========================
    def _sync_ra(self, user):
        RA_USER = config('RA_USER', default='')
        RA_KEY = config('RA_API_KEY', default='')
        
        if not RA_USER or not RA_KEY:
            self.stdout.write(self.style.WARNING("RA: Credenciais ausentes no .env. Pulando."))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(f"--- INICIANDO RA SYNC ({RA_USER}) ---"))
        
        ra_plat, _ = Platform.objects.get_or_create(slug='retroachievements', defaults={'name': 'RetroAchievements'})

        # Pega jogos com progresso
        url = f"https://retroachievements.org/API/API_GetUserCompletedGames.php?z={RA_USER}&y={RA_KEY}&u={RA_USER}"
        try:
            data = requests.get(url).json()
            games = data if isinstance(data, list) else []
        except: return

        self.stdout.write(f"Processando {len(games)} jogos do RA...")

        for g in games:
            ra_id = str(g.get('GameID'))
            title = g.get('Title')
            
            # Master Provisório
            temp_id = int(ra_id) + 900000000
            master, _ = MasterGame.objects.get_or_create(
                title=title,
                defaults={'igdb_id': temp_id}
            )

            p_game, _ = PlatformGame.objects.get_or_create(
                platform=ra_plat, external_id=ra_id,
                defaults={'master_game': master, 'external_title': title}
            )

            entry, _ = UserLibraryEntry.objects.update_or_create(
                user=user, platform_game=p_game,
                defaults={'status': 'playing'}
            )
            
            # Chama sync de conquistas específico pra esse jogo
            self._fetch_ra_achievements(user, entry, RA_USER, RA_KEY)
            time.sleep(0.2) # Rate limit leve

    def _fetch_ra_achievements(self, user, entry, ra_user, ra_key):
        ra_id = entry.platform_game.external_id
        url = f"https://retroachievements.org/API/API_GetGameInfoAndUserProgress.php?z={ra_user}&y={ra_key}&u={ra_user}&g={ra_id}"
        
        try:
            data = requests.get(url).json()
        except: return

        if 'Achievements' not in data or not data['Achievements']: return

        achievements = data['Achievements']
        unlocked_count = 0
        total_count = len(achievements)

        for ach_id, ach_data in achievements.items():
            badge = ach_data.get('BadgeName')
            
            ach_obj, _ = Achievement.objects.update_or_create(
                platform_game=entry.platform_game,
                external_id=str(ach_id),
                defaults={
                    'name': ach_data.get('Title'),
                    'description': ach_data.get('Description'),
                    'xp_value': int(ach_data.get('Points', 0)),
                    'icon_url': f"https://media.retroachievements.org/Badge/{badge}.png" if badge else None
                }
            )

            if ach_data.get('DateEarned'):
                unlocked_count += 1
                try:
                    dt = datetime.strptime(ach_data['DateEarned'], "%Y-%m-%d %H:%M:%S")
                    UserAchievement.objects.get_or_create(
                        user=user, achievement=ach_obj,
                        defaults={'unlocked_at': make_aware(dt)}
                    )
                except: pass

        if unlocked_count == total_count and total_count > 0:
            if entry.status != 'completed':
                entry.status = 'completed'
                entry.save()
                self.stdout.write(self.style.SUCCESS(f"   -> {entry.platform_game.master_game.title} (RA) PLATINADO!"))