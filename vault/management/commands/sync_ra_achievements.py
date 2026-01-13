import requests
import time
from django.core.management.base import BaseCommand
from django.utils.dateparse import parse_datetime
from django.utils.timezone import make_aware
from datetime import datetime
from vault.models import PlatformGame, Achievement, UserAchievement, UserLibraryEntry
from decouple import config

class Command(BaseCommand):
    help = 'Baixa conquistas do RA e atualiza progresso'

    def handle(self, *args, **kwargs):
        USER = config('RA_USER')
        KEY = config('RA_API_KEY')
        
        # Pega apenas jogos do RA que o usuário tem na biblioteca
        ra_entries = UserLibraryEntry.objects.filter(
            platform_game__platform__slug='retroachievements'
        ).select_related('platform_game', 'platform_game__master_game')

        total_games = ra_entries.count()
        self.stdout.write(f'Sincronizando conquistas de {total_games} jogos do RA...')

        for i, entry in enumerate(ra_entries):
            p_game = entry.platform_game
            ra_id = p_game.external_id
            
            # Rate Limit amigável
            time.sleep(0.3)
            
            # Endpoint Mágico: Traz info do jogo E o progresso do usuário de uma vez
            url = f"https://retroachievements.org/API/API_GetGameInfoAndUserProgress.php?z={USER}&y={KEY}&u={USER}&g={ra_id}"
            
            try:
                data = requests.get(url).json()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Erro conexão jogo {ra_id}: {e}'))
                continue

            # Validação básica
            if 'Achievements' not in data:
                continue

            achievements_list = data['Achievements']
            if not achievements_list:
                continue

            self.stdout.write(f'[{i+1}/{total_games}] {p_game.master_game.title}: Processando {len(achievements_list)} conquistas...')

            total_achievements = len(achievements_list)
            unlocked_count = 0

            for ach_id, ach_data in achievements_list.items():
                # 1. Salvar/Atualizar a Conquista (Definição)
                # O RA usa ícones tipo "12345". A URL completa é media.retroachievements.org/Badge/12345.png
                badge_id = ach_data.get('BadgeName', '')
                icon_url = f"https://media.retroachievements.org/Badge/{badge_id}.png"

                achievement_obj, _ = Achievement.objects.update_or_create(
                    platform_game=p_game,
                    external_id=str(ach_id),
                    defaults={
                        'name': ach_data.get('Title'),
                        'description': ach_data.get('Description'),
                        'xp_value': int(ach_data.get('Points', 0)),
                        'icon_url': icon_url,
                        # No RA, DisplayOrder define a ordem. Podemos usar depois.
                    }
                )

                # 2. Salvar o Desbloqueio do Usuário (Se tiver data)
                date_earned = ach_data.get('DateEarned')
                if date_earned:
                    unlocked_count += 1
                    # Converter string de data para formato do Django
                    try:
                        dt_naive = datetime.strptime(date_earned, "%Y-%m-%d %H:%M:%S")
                        dt_aware = make_aware(dt_naive) # Adiciona fuso horário
                        
                        UserAchievement.objects.get_or_create(
                            user=entry.user,
                            achievement=achievement_obj,
                            defaults={'unlocked_at': dt_aware}
                        )
                    except ValueError:
                        pass # Data inválida ou Hardcore mode as vezes buga data

            # 3. Lógica de AUTO-COMPLETE (Zerado)
            is_100_percent = (unlocked_count == total_achievements) and (total_achievements > 0)
            
            if is_100_percent and entry.status != 'completed':
                entry.status = 'completed'
                entry.save()
                self.stdout.write(self.style.SUCCESS(f'   -> PLATINADO! Status atualizado para "Zerado".'))
            
            # Se não é 100% mas tem conquista, garante que ta como playing
            elif unlocked_count > 0 and entry.status == 'backlog':
                entry.status = 'playing'
                entry.save()

        self.stdout.write(self.style.SUCCESS('Sincronização de Conquistas Finalizada!'))