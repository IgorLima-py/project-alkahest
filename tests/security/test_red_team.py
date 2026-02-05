import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from vault.models import UserLibraryEntry, GameList, Review, PlatformGame, MasterGame, Platform
from django.contrib.messages import get_messages
from django.test import override_settings
from django.core.cache import cache
from django.conf import settings

# Mocks para não chamar Celery/Steam de verdade
from unittest.mock import patch

@pytest.mark.django_db
class TestBrokenAccessControl:
    """
    OWASP A01: Broken Access Control (IDOR & Privilege Escalation)
    """

    def test_idor_add_others_entry_to_my_list(self, client, user_a, user_b, master_game, platform):
        pg = PlatformGame.objects.create(master_game=master_game, platform=platform, external_id='123')
        entry_b = UserLibraryEntry.objects.create(user=user_b, platform_game=pg, status='playing')
        list_a = GameList.objects.create(user=user_a, title="My Backlog")
        
        client.force_login(user_a)
        url = reverse('add_to_list', kwargs={'game_id': entry_b.id})
        data = {'list_id': list_a.id}
        
        response = client.post(url, data, secure=True)
        
        if response.status_code == 302:
            pytest.fail("🚨 IDOR DETECTADO: User A conseguiu adicionar um Entry do User B na lista!")
        
        assert response.status_code in [404, 403]

    def test_delete_review_idor(self, client, user_a, user_b, master_game, platform):
        pg = PlatformGame.objects.create(master_game=master_game, platform=platform, external_id='999')
        entry_b = UserLibraryEntry.objects.create(user=user_b, platform_game=pg)
        review_b = Review.objects.create(user=user_b, library_entry=entry_b, text="Hate it", rating=10)
        
        client.force_login(user_a)
        url = reverse('delete_review', kwargs={'review_id': review_b.id})
        
        response = client.post(url, secure=True)
        assert response.status_code == 404
        assert Review.objects.filter(id=review_b.id).exists()

@pytest.mark.django_db
class TestInjectionAndSanitization:
    """
    OWASP A03: Injection (XSS)
    """

    def test_stored_xss_in_review(self, client, user_a, entry_user_a):
        client.force_login(user_a)
        url = reverse('game_detail', kwargs={'game_id': entry_user_a.id})
        xss_payload = "Nice game <img src=x onerror=alert('HACKED')>"
        
        data = {
            'create_review': '1',
            'text': xss_payload,
            'rating': 100,
            'is_recommended': True
        }
        
        response = client.post(url, data, follow=True, secure=True)
        assert response.status_code == 200
        review = Review.objects.get(library_entry=entry_user_a)
        
        assert "onerror" not in review.text_html
        assert "<script>" not in review.text_html

@pytest.mark.django_db
class TestDenialOfService:
    """
    OWASP A04: Insecure Design (Lack of Rate Limiting)
    """

    @override_settings(
        CACHES={
            'default': {
                'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
                'LOCATION': 'unique-snowflake-v2',
            }
        },
        RATELIMIT_USE_CACHE='default',
        RATELIMIT_ENABLE=True,
    )
    @patch('vault.views.app.send_task') 
    def test_celery_bomb_sync_steam(self, mock_send_task, client):
        """
        EXPLOIT: Disparar trigger de sync repetidamente.
        Deve bloquear usuário COMUM.
        """
        cache.clear()

        # Cria usuário comum
        spammer = User.objects.create_user(
            username='spammer_final', 
            password='123',
            is_staff=False
        )
        
        # URL do alvo
        url = reverse('trigger_steam_sync')
        
        status_codes = []
        
        # Truque: Usamos REMOTE_ADDR fixo para garantir que o RateLimit
        # identifique a origem inequivocamente, mesmo se falhar em pegar o User ID.
        fixed_ip = '127.0.0.66'
        
        # Fazemos o Login MANUALMENTE na sessão para ter certeza absoluta
        client.login(username='spammer_final', password='123')

        print("\n--- INICIANDO BOMBARDEIO ---")
        for i in range(20): # Aumentei para 20 pra ter certeza
            # Passamos REMOTE_ADDR explicitamente no extra keyword args do post
            resp = client.post(url, secure=True, REMOTE_ADDR=fixed_ip)
            status_codes.append(resp.status_code)
            print(f"Req {i+1}: {resp.status_code}")
        
        # Verifica se houve bloqueio (403 ou 429)
        assert 403 in status_codes or 429 in status_codes, \
            f"FALHA: Rate Limit ignorado. Codes: {status_codes}"