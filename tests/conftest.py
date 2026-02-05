# tests/conftest.py
import pytest
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from vault.models import MasterGame, Platform

@pytest.fixture
def client():
    """Client padrão do Django para fazer requests"""
    from django.test import Client
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
