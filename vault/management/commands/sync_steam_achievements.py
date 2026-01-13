import requests
import time
from datetime import datetime
from django.core.management.base import BaseCommand
from django.utils.timezone import make_aware
from vault.models import UserLibraryEntry, Achievement, UserAchievement
from decouple import config

class Command(BaseCommand):
    help = 'Sincroniza conquistas da Steam (Schema + Progresso User)'

    def handle(self, *args, **kwargs):
        KEY = config('STEAM_API_KEY')
        STEAM_ID = config('STEAM_ID')

        # Filtra apenas jogos da Steam que o usuário tem na biblioteca
        steam_entries = UserLibraryEntry.objects.filter(
            platform_game__platform__slug='steam'
        ).select_related('platform_game', 'platform_game__master_game')

        total_games = steam_entries.count()
        self.stdout.write(f'Iniciando sync para {total_games} jogos da Steam...')

        for index, entry in enumerate(steam_entries):
            p_game = entry.platform_game
            app_id = p_game.external_id
            
            # Respeitar Rate Limit da Steam
            time.sleep(0.5)

            # --- PASSO 1: Buscar o SCHEMA (Dados dos troféus: Nome, Ícone) ---
            # Endpoint: GetSchemaForGame
            schema_url = f"http://api.steampowered.com/ISteamUserStats/GetSchemaForGame/v2/?key={KEY}&appid={app_id}"
            
            try:
                schema_res = requests.get(schema_url)
                schema_data = schema_res.json()
            except Exception:
                self.stdout.write(self.style.ERROR(f'Erro conexão Schema: {p_game.external_title}'))
                continue

            # Se o jogo não tem stats ou conquistas, a Steam retorna vazio ou erro
            if not schema_data.get('game', {}).get('availableGameStats', {}).get('achievements'):
                self.stdout.write(f'[{index+1}/{total_games}] {p_game.master_game.title}: Sem conquistas (Skipping)')
                continue

            # Mapear Schema (API Name -> Dados Reais)
            # Ex: "NEW_ACHIEVEMENT_1_0" -> {"name": "First Blood", "icon": "url..."}
            ach_definitions = {}
            raw_achievements = schema_data['game']['availableGameStats']['achievements']
            
            for raw in raw_achievements:
                api_name = raw['name']
                ach_definitions[api_name] = {
                    'name': raw['displayName'],
                    'description': raw.get('description', ''), # Algumas não têm descrição (hidden)
                    'icon': raw['icon'],
                    'icon_gray': raw['icongray']
                }

            # --- PASSO 2: Buscar o PROGRESSO DO USUÁRIO ---
            # Endpoint: GetPlayerAchievements
            user_url = f"http://api.steampowered.com/ISteamUserStats/GetPlayerAchievements/v0001/?appid={app_id}&key={KEY}&steamid={STEAM_ID}"
            
            try:
                user_res = requests.get(user_url)
                user_data = user_res.json()
            except Exception:
                continue

            # Verifica se retornou sucesso (alguns jogos perfil privado bloqueia)
            if not user_data.get('playerstats', {}).get('success'):
                self.stdout.write(self.style.WARNING(f'   -> Falha ao ler stats de usuário para {p_game.master_game.title}'))
                continue

            user_achievements = user_data['playerstats'].get('achievements', [])
            
            self.stdout.write(f'[{index+1}/{total_games}] {p_game.master_game.title}: Processando {len(user_achievements)} conquistas...')

            # --- PASSO 3: Salvar no Banco ---
            unlocked_count = 0
            total_count = len(user_achievements)

            for u_ach in user_achievements:
                api_name = u_ach['apiname']
                is_unlocked = u_ach['achieved'] == 1
                unlock_time = u_ach['unlocktime'] # Timestamp Unix

                # Pegar dados bonitos do Schema
                definition = ach_definitions.get(api_name)
                if not definition:
                    continue # Conquista existe no user mas não no schema (bizarro, mas acontece)

                # Criar/Atualizar a Conquista no Banco
                achievement_obj, _ = Achievement.objects.update_or_create(
                    platform_game=p_game,
                    external_id=api_name, # Na Steam o ID é o "apiname"
                    defaults={
                        'name': definition['name'],
                        'description': definition['description'],
                        'icon_url': definition['icon'],
                        'xp_value': 10 # Valor fixo por enquanto
                    }
                )

                # Registrar Desbloqueio
                if is_unlocked:
                    unlocked_count += 1
                    # Converter timestamp para data
                    dt_aware = make_aware(datetime.fromtimestamp(unlock_time))
                    
                    UserAchievement.objects.get_or_create(
                        user=entry.user,
                        achievement=achievement_obj,
                        defaults={'unlocked_at': dt_aware}
                    )

            # --- PASSO 4: Auto-Complete (Zerado) ---
            if unlocked_count == total_count and total_count > 0 and entry.status != 'completed':
                entry.status = 'completed'
                entry.save()
                self.stdout.write(self.style.SUCCESS('   -> PLATINADO NA STEAM!'))
            
            elif unlocked_count > 0 and entry.status == 'backlog':
                entry.status = 'playing'
                entry.save()

        self.stdout.write(self.style.SUCCESS('Sync Steam Finalizado!'))