import pytest
from django.contrib.auth.models import User
from django.test import Client
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