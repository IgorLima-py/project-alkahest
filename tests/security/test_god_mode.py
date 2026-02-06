import pytest
from django.contrib.auth.models import User
from vault.models import MasterGame, PlatformGame, UserLibraryEntry, Review, GameListItem, GameList, Platform
from django.urls import reverse

@pytest.mark.django_db
def test_merge_games_logic(client):
    # --- SETUP (Criação Manual de Objetos) ---
    
    # 1. Usuários
    admin_user = User.objects.create_superuser('admin', 'admin@example.com', 'password123')
    normal_user = User.objects.create_user('user', 'user@example.com', 'password123')
    
    # 2. Plataforma
    platform = Platform.objects.create(name="Steam", slug="steam")
    
    # 3. Target (O Jogo Oficial)
    target_game = MasterGame.objects.create(title="The Witcher 3: Wild Hunt", igdb_id=111)
    target_pg = PlatformGame.objects.create(
        master_game=target_game, 
        platform=platform, 
        external_id="111", 
        external_title="Witcher 3 WH"
    )
    
    # 4. Source (O Duplicado a ser deletado)
    source_game = MasterGame.objects.create(title="Witcher 3 (Dup)", igdb_id=222)
    source_pg = PlatformGame.objects.create(
        master_game=source_game, 
        platform=platform, 
        external_id="222", 
        external_title="Witcher 3"
    )
    
    # 5. O Usuário tem o jogo SOURCE na biblioteca (com review)
    entry_source = UserLibraryEntry.objects.create(
        user=normal_user, 
        platform_game=source_pg, 
        status='playing',
        playtime_minutes=100
    )
    review_source = Review.objects.create(
        user=normal_user, 
        library_entry=entry_source, 
        text="Review do jogo duplicado", 
        rating=90
    )
    
    # 6. Conflito: O Usuário TAMBÉM tem o jogo TARGET numa lista
    game_list = GameList.objects.create(user=normal_user, title="My Backlog")
    GameListItem.objects.create(game_list=game_list, master_game=target_game, order=1)
    GameListItem.objects.create(game_list=game_list, master_game=source_game, order=2) # Item que deve sumir

    # --- EXECUÇÃO ---
    client.force_login(admin_user)
    
    url = reverse('merge_games_tool')
    data = {
        'source_id': source_game.id,
        'target_id': target_game.id
    }
    
    response = client.post(url, data, follow=True)
    
    # --- VALIDAÇÃO (ASSERTS) ---
    assert response.status_code == 200
    
    # Verifica se a mensagem de sucesso apareceu
    messages = list(response.context['messages'])
    assert len(messages) > 0
    assert "SUCESSO" in str(messages[0])
    
    # A) Source foi deletado?
    assert not MasterGame.objects.filter(id=source_game.id).exists()
    
    # B) Target existe?
    assert MasterGame.objects.filter(id=target_game.id).exists()
    
    # C) Library Entry foi migrada?
    # O user agora deve ter uma entry apontando para o TARGET PG
    target_entry = UserLibraryEntry.objects.get(user=normal_user, platform_game=target_pg)
    assert target_entry.playtime_minutes == 100 # Dado preservado
    assert target_entry.status == 'playing'
    
    # D) Review foi re-apontada?
    review = Review.objects.get(id=review_source.id)
    assert review.library_entry == target_entry # Aponta pro novo entry
    
    # E) Listas limpas?
    # O source sumiu da lista, ficou só o target (sem duplicata)
    assert GameListItem.objects.filter(game_list=game_list).count() == 1
    assert GameListItem.objects.filter(game_list=game_list, master_game=target_game).exists()

@pytest.mark.django_db
def test_merge_security_idor(client):
    """Garante que usuários normais não podem acessar a ferramenta de merge."""
    hacker = User.objects.create_user('hacker', 'hacker@example.com', 'password123')
    client.force_login(hacker)
    
    url = reverse('merge_games_tool')
    
    # Deve redirecionar para login (admin required)
    response = client.get(url)
    
    # O decorador @user_passes_test redireciona (302) para o login se falhar
    assert response.status_code == 302 
    assert "/login/" in response.url 
