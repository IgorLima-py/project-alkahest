import pytest
from django.urls import reverse
from django.contrib.auth.models import User
from vault.models import UserLibraryEntry, GameList, Review, PlatformGame, MasterGame, Platform
from django.contrib.messages import get_messages
from django.test import override_settings
from django.core.cache import cache

# Mocks para não chamar Celery/Steam de verdade
from unittest.mock import patch

@pytest.mark.django_db
class TestBrokenAccessControl:
    """
    OWASP A01: Broken Access Control (IDOR & Privilege Escalation)
    """

    def test_idor_add_others_entry_to_my_list(self, client, user_a, user_b, master_game, platform):
        """
        EXPLOIT: User A tenta adicionar um UserLibraryEntry privado do User B 
        dentro de sua própria lista (User A).
        """
        # Setup: User B tem um jogo (entry_b)
        pg = PlatformGame.objects.create(master_game=master_game, platform=platform, external_id='123')
        entry_b = UserLibraryEntry.objects.create(user=user_b, platform_game=pg, status='playing')
        
        # Setup: User A tem uma lista
        list_a = GameList.objects.create(user=user_a, title="My Backlog")
        
        # Login como User A (Atacante)
        client.force_login(user_a)
        
        # Ação: Tentar adicionar o game_id (UUID) do User B na lista do User A
        url = reverse('add_to_list', kwargs={'game_id': entry_b.id})
        data = {'list_id': list_a.id}
        
        response = client.post(url, data, secure=True)
        
        # EXPECTATIVA DE SEGURANÇA: 
        # O sistema deveria bloquear (404 ou 403) porque entry_b não é do User A.
        # SE RETORNAR 302 (Redirect), O TESTE FALHA -> VOCÊ TEM UM IDOR.
        if response.status_code == 302:
            pytest.fail("🚨 IDOR DETECTADO: User A conseguiu adicionar um Entry do User B na lista!")
        
        assert response.status_code in [404, 403]

    def test_delete_review_idor(self, client, user_a, user_b, master_game, platform):
        """
        EXPLOIT: User A tenta deletar review do User B.
        """
        pg = PlatformGame.objects.create(master_game=master_game, platform=platform, external_id='999')
        entry_b = UserLibraryEntry.objects.create(user=user_b, platform_game=pg)
        review_b = Review.objects.create(user=user_b, library_entry=entry_b, text="Hate it", rating=10)
        
        client.force_login(user_a)
        url = reverse('delete_review', kwargs={'review_id': review_b.id})
        
        response = client.post(url, secure=True)
        
        # O get_object_or_404(user=request.user) deve proteger isso
        assert response.status_code == 404, "Falha: User A conseguiu deletar (ou ver) review do User B"
        assert Review.objects.filter(id=review_b.id).exists(), "O review foi deletado do banco!"

@pytest.mark.django_db
class TestInjectionAndSanitization:
    """
    OWASP A03: Injection (XSS)
    """

    def test_stored_xss_in_review(self, client, user_a, entry_user_a):
        """
        EXPLOIT: Injetar Payload XSS no corpo do Review.
        """
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
        
        # Verifica no Banco de Dados
        review = Review.objects.get(library_entry=entry_user_a)
        
        # O nh3 deve remover o onerror ou escapar a tag
        assert "onerror" not in review.text_html, "FALHA: Event handler JS persistiu no HTML sanitizado!"
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
                'LOCATION': 'unique-snowflake',
            }
        },
        RATELIMIT_USE_CACHE='default',
        RATELIMIT_ENABLE=True
    )
    # O 'patch' finge que o send_task funciona sem chamar o worker real
    @patch('vault.views.app.send_task') 
    def test_celery_bomb_sync_steam(self, mock_send_task, client):
        """
        EXPLOIT: Disparar trigger de sync repetidamente.
        Deve bloquear usuário COMUM.
        """
        # Garante cache limpo antes de começar
        cache.clear()

        # CRIA UM USER COMUM (NÃO-STAFF) PARA O RATE LIMIT PEGAR
        spammer = User.objects.create_user(
            username='spammer_bot_v4', 
            password='123',
            is_staff=False,
            is_superuser=False
        )
        client.force_login(spammer)
        
        url = reverse('trigger_steam_sync')
        
        # Dispara 15 requisições seguidas (limite na view é 10/h)
        status_codes = []
        for _ in range(15):
            resp = client.post(url, secure=True)
            status_codes.append(resp.status_code)
        
        # Debug para você ver o que aconteceu
        print(f"Status Codes (Spammer): {status_codes}")
        
        # Se o Rate Limit estiver funcionando, veremos 429 ou 403
        assert 429 in status_codes or 403 in status_codes, \
            f"FALHA: Nenhuma requisição foi bloqueada! O spammer passou livre. Codes: {status_codes}"
