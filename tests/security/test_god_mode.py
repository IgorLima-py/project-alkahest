import pytest
from vault.models import MasterGame, PlatformGame, UserLibraryEntry, Review, GameListItem, GameList
from vault.forms import GameMergeForm
from django.urls import reverse

@pytest.mark.django_db
def test_merge_games_logic(user_factory, master_game_factory, platform_factory):
    # 1. Setup: User, Platform e 2 Jogos (Duplicados)
    admin_user = user_factory(is_superuser=True)
    normal_user = user_factory()
    platform = platform_factory(name="Steam", slug="steam")
    
    # Target (O Oficial)
    target_game = master_game_factory(title="The Witcher 3: Wild Hunt", igdb_id=111)
    target_pg = PlatformGame.objects.create(master_game=target_game, platform=platform, external_id="111")
    
    # Source (O Duplicado a ser deletado)
    source_game = master_game_factory(title="Witcher 3", igdb_id=222)
    source_pg = PlatformGame.objects.create(master_game=source_game, platform=platform, external_id="222")
    
    # O usuário tem o jogo SOURCE na biblioteca (e fez review)
    entry_source = UserLibraryEntry.objects.create(
        user=normal_user, 
        platform_game=source_pg, 
        status='playing',
        playtime_minutes=100
    )
    review_source = Review.objects.create(user=normal_user, library_entry=entry_source, text="Top", rating=90)
    
    # O usuário TAMBÉM tem o jogo TARGET na lista (Caso de conflito)
    game_list = GameList.objects.create(user=normal_user, title="My Backlog")
    GameListItem.objects.create(game_list=game_list, master_game=target_game)
    GameListItem.objects.create(game_list=game_list, master_game=source_game) # Item duplicado na lista

    # 2. Executar o Merge (via POST na view)
    client = pytest.Client()
    client.force_login(admin_user)
    
    url = reverse('merge_games_tool')
    data = {
        'source_id': source_game.id,
        'target_id': target_game.id
    }
    
    response = client.post(url, data, follow=True)
    
    # 3. Asserts (Verificações)
    assert response.status_code == 200
    assert "Merged" in [m.message for m in response.context['messages']]
    
    # A) Source foi deletado?
    assert not MasterGame.objects.filter(id=source_game.id).exists()
    
    # B) Target existe?
    assert MasterGame.objects.filter(id=target_game.id).exists()
    
    # C) Library Entry foi migrada?
    # O user agora deve ter uma entry apontando para o TARGET PG, mas com os dados preservados
    target_entry = UserLibraryEntry.objects.get(user=normal_user, platform_game=target_pg)
    assert target_entry.playtime_minutes == 100 # Dado migrado
    assert target_entry.status == 'playing'
    
    # D) Review foi re-apontada?
    review = Review.objects.get(id=review_source.id)
    assert review.library_entry == target_entry # Aponta pro novo entry
    
    # E) Listas limpas?
    # O usuário tinha os 2 na lista. O merge deve ter removido o source e mantido o target, sem duplicar.
    assert GameListItem.objects.filter(game_list=game_list, master_game=target_game).count() == 1

@pytest.mark.django_db
def test_merge_security_idor(client, user_factory):
    """Garante que usuários normais não podem acessar a ferramenta de merge."""
    hacker = user_factory(is_superuser=False)
    client.force_login(hacker)
    url = reverse('merge_games_tool')
    
    # Deve redirecionar para login (admin required) ou 403, dependendo do user_passes_test
    # O user_passes_test redireciona para login url padrão se falhar
    response = client.get(url)
    assert response.status_code == 302 
    assert "/accounts/login/" in response.url
