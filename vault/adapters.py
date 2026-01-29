from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from allauth.account.utils import user_field
from django.shortcuts import redirect
import uuid

class AlkahestSocialAdapter(DefaultSocialAccountAdapter):
    def populate_user(self, request, sociallogin, data):
        """
        Hook executado antes de criar o usuário.
        Garante que temos um username válido mesmo se a Steam mandar caracteres estranhos.
        """
        user = super().populate_user(request, sociallogin, data)
        
        # Steam retorna o 'personaname' como username, que pode ter caracteres inválidos para URL/DB
        username = data.get('username') or data.get('name') or ''
        
        # Se o username for vazio ou tiver caracteres perigosos, gera um aleatório seguro
        if not username.isalnum():
            # Gera ex: user_a1b2c3d4
            safe_id = uuid.uuid4().hex[:8]
            user_field(user, 'username', f"steam_user_{safe_id}")
        
        return user

    def pre_social_login(self, request, sociallogin):
        """
        Intervém antes do login completar.
        Se a Steam não mandar e-mail (comum), o Allauth normalmente pede para o usuário digitar.
        Aqui podemos forçar lógicas extras se necessário.
        """
        # Por padrão, o Allauth já redireciona para uma tela de "Signup" pedindo e-mail 
        # se o provider não fornecer. Não precisamos reinventar a roda aqui, 
        # apenas garantir que o fluxo siga.
        pass

    def save_user(self, request, sociallogin, form=None):
        """
        Executado logo após o usuário ser salvo no banco.
        Garante a criação do UserProfile.
        """
        user = super().save_user(request, sociallogin, form)
        
        from .models import UserProfile
        # Garante que não quebre o dashboard por falta de perfil
        UserProfile.objects.get_or_create(user=user)
        
        return user
