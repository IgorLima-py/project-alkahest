import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.core.management import call_command
from django.db import connections
from vault.models import MasterGame, Platform, PlatformGame, UserLibraryEntry
import uuid

@pytest.fixture
def client():
    return Client()

@pytest.fixture
def user_a(db):
    """Usuário Vítima"""
    return User.objects.create_user(username='victim', email='victim@alkahest.gg', password='password123')

@pytest.fixture
def user_b(db):
    """Usuário Atacante"""
    return User.objects.create_user(username='attacker', email='attacker@hacker.com', password='password123')

@pytest.fixture
def platform(db):
    return Platform.objects.create(name="Steam", slug="steam")

@pytest.fixture
def master_game(db):
    return MasterGame.objects.create(title="Elden Ring", igdb_id=12345)

@pytest.fixture
def entry_user_a(db, user_a, master_game, platform):
    """
    Cria um UserLibraryEntry pertencente ao User A.
    Necessário para testes de XSS e edição.
    """
    # Garante que o vínculo PlatformGame existe
    pg, _ = PlatformGame.objects.get_or_create(
        master_game=master_game, 
        platform=platform,
        defaults={
            'external_id': 'fix_123', 
            'external_title': 'Elden Ring Steam'
        }
    )
    
    # Cria a entrada na biblioteca
    return UserLibraryEntry.objects.create(
        user=user_a, 
        platform_game=pg, 
        status='playing',
        id=uuid.uuid4()
    )


@pytest.fixture(autouse=True)
def cleanup_db_connections():
    """Força o fechamento de conexões após cada teste para evitar DB Lock"""
    from django.db import connections
    yield
    for conn in connections.all():
        conn.close()


@pytest.fixture(scope='session', autouse=True)
def django_db_setup(django_db_setup, django_db_blocker):
    """
    Garante que o banco de teste seja recriado se necessário.
    Fecha conexões antigas para evitar locks no SQLite.
    """
    with django_db_blocker.unblock():
        # Força o fechamento de todas as conexões antigas
        for conn in connections.all():
            conn.close()

@pytest.fixture(autouse=True)
def enable_db_access_for_all_tests(db):
    """
    Habilita acesso ao banco em todos os testes automaticamente.
    Remove a necessidade de decorar cada teste com @pytest.mark.django_db
    """
    pass