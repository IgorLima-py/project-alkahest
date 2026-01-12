import requests
from django.core.management.base import BaseCommand
from django.conf import settings
from vault.models import Platform, PlatformGame, MasterGame, UserLibraryEntry
from django.contrib.auth.models import User
from decouple import config

class Command(BaseCommand):
    help = 'Importa jogos da Steam para o banco de dados'

    def handle(self, *args, **kwargs):
        # 1. Configurações iniciais
        KEY = config('STEAM_API_KEY')
        STEAM_ID = config('STEAM_ID')
        
        if not KEY or not STEAM_ID:
            self.stdout.write(self.style.ERROR('ERRO: Configure o .env com STEAM_API_KEY e STEAM_ID'))
            return

        self.stdout.write(f'Conectando à Steam para buscar jogos do ID {STEAM_ID}...')

        # 2. Batendo na API da Steam (Endpoint: GetOwnedGames)
        url = f"http://api.steampowered.com/IPlayerService/GetOwnedGames/v0001/?key={KEY}&steamid={STEAM_ID}&include_appinfo=1&format=json"
        
        try:
            response = requests.get(url)
            data = response.json()
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Erro na conexão: {e}'))
            return

        games_list = data.get('response', {}).get('games', [])
        self.stdout.write(self.style.SUCCESS(f'{len(games_list)} jogos encontrados. Iniciando importação...'))

        # 3. Pegando o usuário Admin (vamos atribuir os jogos a ele por enquanto)
        user = User.objects.first() # Pega o primeiro usuário (você)
        
        # 4. Pegando a plataforma Steam do banco
        try:
            steam_platform = Platform.objects.get(slug='steam')
        except Platform.DoesNotExist:
            self.stdout.write(self.style.ERROR('ERRO: Plataforma "steam" não cadastrada no banco. Crie ela no Admin.'))
            return

        # 5. O Loop de ETL
        count_novos = 0
        for game in games_list:
            app_id = str(game.get('appid'))
            title = game.get('name')
            playtime_forever = game.get('playtime_forever', 0) # Em minutos

            # --- Lógica Temporária de "Master Game" ---
            # Como não temos o IGDB ainda, vamos criar um MasterGame 
            # com o mesmo nome da Steam se ele não existir.
            # get_or_create retorna uma tupla (objeto, boolean_se_foi_criado)
            master_game, created = MasterGame.objects.get_or_create(
                title=title,
                defaults={'igdb_id': int(app_id)} # Hack temporário: usar ID da steam como ID do IGDB pra não quebrar
            )

            # --- Criar o Jogo da Plataforma ---
            platform_game, _ = PlatformGame.objects.get_or_create(
                platform=steam_platform,
                external_id=app_id,
                defaults={
                    'master_game': master_game,
                    'external_title': title
                }
            )

            # --- Adicionar à Biblioteca do Usuário ---
            # update_or_create: Se já tem, atualiza o tempo de jogo. Se não tem, cria.
            library_entry, created = UserLibraryEntry.objects.update_or_create(
                user=user,
                platform_game=platform_game,
                defaults={
                    'playtime_minutes': playtime_forever,
                    'status': 'playing' if playtime_forever > 0 else 'backlog' # Lógica simples de status
                }
            )
            
            if created:
                count_novos += 1
                # Imprime um pontinho pra não poluir a tela, igual barra de progresso
                self.stdout.write('.', ending='') 

        self.stdout.write(self.style.SUCCESS(f'\nConcluído! {count_novos} novos jogos importados.'))