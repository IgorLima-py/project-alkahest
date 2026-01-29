from django.core.management.base import BaseCommand
from vault.tasks import enrich_library_task

class Command(BaseCommand):
    help = 'Dispara o enriquecimento de metadados via Celery (IGDB)'

    def handle(self, *args, **options):
        self.stdout.write("🧠 Enviando solicitação de Inteligência (Enrich) para o Worker...")
        
        # Dispara a task sem travar o terminal
        enrich_library_task.delay()
        
        self.stdout.write(self.style.SUCCESS("✅ Task enviada! O Worker vai buscar capas e dados no IGDB em background."))
