import requests
from django.core.management.base import BaseCommand
from vault.models import Platform, PlatformGame, MasterGame, UserLibraryEntry
from django.contrib.auth.models import User
from decouple import config

class Command(BaseCommand):
    help = 'Importa jogos do RetroAchievements. Uso: python manage.py import_ra --user NomeDoUsuario'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Nome do usuário no RA para importar')

    def handle(self, *args, **kwargs):
        # 1. Configuração
        ENV_USER = config('RA_USER', default='')
        KEY = config('RA_API_KEY')
        
        # Se passar --user no comando, usa ele. Se não, usa o do .env
        TARGET_USER = kwargs['user'] if kwargs['user'] else ENV_USER

        if not TARGET_USER or not KEY:
            self.stdout.write(self.style.ERROR('Erro: Precisa de um usuário (no .env ou via --user) e API Key.'))
            return

        self.stdout.write(f'Buscando jogos de: {TARGET_USER}...')

        # 2. API do RA (GetUserRecentlyPlayedGames)
        # Vamos pegar 50 jogos para teste
        url = f"https://retroachievements.org/API/API_GetUserRecentlyPlayedGames.php?z={TARGET_USER}&y={KEY}&u={TARGET_USER}&c=50"
        
        try:
            response = requests.get(url)
            data = response.json()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro conexão: {e}'))
            return

        if not data:
            self.stdout.write(self.style.WARNING(f'Nenhum jogo encontrado para {TARGET_USER}.'))
            return

        # 3. Setup de Banco
        # Vamos usar o primeiro usuário do banco (você) para salvar os dados, 
        # ou criar um usuário de teste se preferir não sujar o seu.
        user = User.objects.first() 
        
        ra_platform, _ = Platform.objects.get_or_create(slug='retroachievements', defaults={'name': 'RetroAchievements'})

        count = 0
        for game in data:
            ra_id = str(game.get('GameID'))
            title = game.get('Title')
            console_name = game.get('ConsoleName')
            
            # Título único para não confundir com Steam por enquanto
            display_title = f"{title} ({console_name})"
            
            # --- Criação do Master Game ---
            # Aqui está o pulo do gato: Por enquanto criamos sem IGDB ID real.
            # O script de enrich (enriquecimento) que vai ter que se virar pra achar isso depois.
            master_game, created = MasterGame.objects.get_or_create(
                title=title, # Usa o titulo limpo
                defaults={'igdb_id': int(ra_id) + 9000000} # ID Provisório
            )

            # --- Criação do Jogo na Plataforma ---
            platform_game, _ = PlatformGame.objects.get_or_create(
                platform=ra_platform,
                external_id=ra_id,
                defaults={
                    'master_game': master_game,
                    'external_title': display_title
                }
            )

            # --- Vínculo com Usuário ---
            UserLibraryEntry.objects.update_or_create(
                user=user,
                platform_game=platform_game,
                defaults={'status': 'playing'}
            )
            count += 1
            self.stdout.write(f'Importado: {display_title}')

        self.stdout.write(self.style.SUCCESS(f'Sucesso! {count} jogos importados de {TARGET_USER}.'))