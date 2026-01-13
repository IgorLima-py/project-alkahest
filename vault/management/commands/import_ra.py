import requests
from django.core.management.base import BaseCommand
from vault.models import Platform, PlatformGame, MasterGame, UserLibraryEntry
from django.contrib.auth.models import User
from decouple import config

class Command(BaseCommand):
    help = 'Importa biblioteca do RA (Jogos com pelo menos 1 conquista)'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Nome do usuário no RA')

    def handle(self, *args, **kwargs):
        ENV_USER = config('RA_USER', default='')
        KEY = config('RA_API_KEY')
        TARGET_USER = kwargs['user'] if kwargs['user'] else ENV_USER

        if not TARGET_USER or not KEY:
            self.stdout.write(self.style.ERROR('Erro: Precisa de User e API Key.'))
            return

        self.stdout.write(f'Baixando histórico completo de: {TARGET_USER}...')

        # MUDANÇA: Usando GetUserCompletedGames (Traz tudo que tem progresso)
        url = f"https://retroachievements.org/API/API_GetUserCompletedGames.php?z={TARGET_USER}&y={KEY}&u={TARGET_USER}"
        
        try:
            response = requests.get(url)
            data = response.json()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro conexão: {e}'))
            return

        # Esse endpoint retorna um dicionário, não lista direta as vezes, ou lista
        if not data:
            self.stdout.write(self.style.WARNING(f'Nada encontrado.'))
            return

        user = User.objects.first()
        ra_platform, _ = Platform.objects.get_or_create(slug='retroachievements', defaults={'name': 'RetroAchievements'})

        count = 0
        # O RA as vezes retorna os jogos dentro de uma chave 'results' ou direto.
        # Vamos garantir que iteramos na lista
        games_list = data if isinstance(data, list) else data.get('results', [])

        for game in games_list:
            ra_id = str(game.get('GameID'))
            title = game.get('Title')
            console_name = game.get('ConsoleName')
            
            # Master Game (ID Provisório)
            master_game, _ = MasterGame.objects.get_or_create(
                title=title, 
                defaults={'igdb_id': int(ra_id) + 9000000} 
            )

            # Platform Game
            display_title = f"{title} ({console_name})"
            platform_game, _ = PlatformGame.objects.get_or_create(
                platform=ra_platform,
                external_id=ra_id,
                defaults={
                    'master_game': master_game,
                    'external_title': display_title
                }
            )

            # Library Entry
            UserLibraryEntry.objects.update_or_create(
                user=user,
                platform_game=platform_game,
                defaults={'status': 'playing'} # Assume jogando se tem conquista
            )
            
            count += 1
            if count % 50 == 0: self.stdout.write(f'{count} jogos processados...')

        self.stdout.write(self.style.SUCCESS(f'Importação Finalizada! {count} jogos encontrados.'))