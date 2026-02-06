import os
import django
from django.db import connection

# Configura o ambiente Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

def kill_test_db_connections():
    db_name = 'test_neondb' # Nome padrão que o pytest-django usa
    print(f"🔪 Procurando conexões zumbis no banco '{db_name}'...")
    
    with connection.cursor() as cursor:
        # sql para matar conexões
        sql = """
        SELECT pg_terminate_backend(pg_stat_activity.pid)
        FROM pg_stat_activity
        WHERE pg_stat_activity.datname = %s
          AND pid <> pg_backend_pid();
        """
        cursor.execute(sql, [db_name])
        row = cursor.fetchone()
        
    print("✅ Conexões encerradas com sucesso. Agora o Pytest pode rodar.")

if __name__ == "__main__":
    try:
        kill_test_db_connections()
    except Exception as e:
        print(f"❌ Erro (talvez o banco nem exista, o que é bom): {e}")
