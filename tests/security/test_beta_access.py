import pytest
from django.conf import settings
from django.urls import reverse
from vault.models import BetaInvite

@pytest.mark.django_db
def test_beta_middleware_blocks_access(client):
    """Visitante sem código deve ser barrado"""
    # Garante que beta está ativo para o teste
    with pytest.MonkeyPatch().context() as m:
        m.setattr(settings, 'BETA_ACTIVE', True)
        response = client.get(reverse('dashboard')) # Tenta acessar dashboard
        assert response.status_code == 302
        assert 'beta-login' in response.url

@pytest.mark.django_db
def test_beta_invite_flow_success(client):
    """Visitante com código entra"""
    invite = BetaInvite.objects.create(code='WELCOME-2026', max_uses=5)
    
    # 1. Posta o código
    response = client.post(reverse('beta_login'), {'invite_code': 'WELCOME-2026'})
    assert response.status_code == 302 # Redireciona para Login
    
    # 2. Sessão deve estar marcada
    assert client.session.get('has_beta_access') is True
    
    # 3. Acesso liberado
    response = client.get(reverse('login'))
    assert response.status_code == 200

@pytest.mark.django_db
def test_beta_invite_limit(client):
    """Código esgotado não passa"""
    invite = BetaInvite.objects.create(code='SOLO-TICKET', max_uses=1, used_count=1)
    
    response = client.post(reverse('beta_login'), {'invite_code': 'SOLO-TICKET'})
    assert response.status_code == 200 # Fica na página (erro)
    assert "expired" in response.content.decode()
    assert client.session.get('has_beta_access') is None
