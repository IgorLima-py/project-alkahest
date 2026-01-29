from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from vault.tasks import sync_steam_library_task, sync_ra_library_task

class Command(BaseCommand):
    help = 'Dispara a sincronização em Background (Celery)'

    def add_arguments(self, parser):
        parser.add_argument('--target', type=str, default='all', help='steam, ra, ou all')
        parser.add_argument('--user', type=str, help='Username do usuário')

    def handle(self, *args, **options):
        target = options['target']
        username = options['user']

        # 1. Pega o usuário
        if username:
            user = User.objects.filter(username=username).first()
        else:
            user = User.objects.filter(is_superuser=True).first()
        
        if not user:
            self.stdout.write(self.style.ERROR("Usuário não encontrado."))
            return

        self.stdout.write(f"📡 Enviando sinal para o Worker (User: {user.username})...")

        # 2. Dispara Steam (se solicitado)
        if target in ['steam', 'all']:
            # .delay() é o que manda pro Redis/Celery
            sync_steam_library_task.delay(user.id) 
            self.stdout.write(self.style.SUCCESS("✅ Task da Steam enviada para a fila!"))

        # 3. Dispara RA (se solicitado)
        if target in ['ra', 'all']:
            sync_ra_library_task.delay(user.id)
            self.stdout.write(self.style.SUCCESS("✅ Task do RetroAchievements enviada para a fila!"))

        self.stdout.write("---")
        self.stdout.write("O terminal está livre. Acompanhe o progresso na janela do Celery Worker.")