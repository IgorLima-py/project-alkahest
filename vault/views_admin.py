from django.shortcuts import render, redirect
from django.contrib.auth.decorators import user_passes_test
from django.db import transaction
from django.contrib import messages
from django.db.models import Sum
from .models import (
    MasterGame, PlatformGame, UserLibraryEntry, Review, 
    GameTip, GameListItem, UserAchievement
)
from .forms import GameMergeForm

# Helper de Segurança: Só Admin entra
def is_superuser(user):
    return user.is_superuser

@user_passes_test(is_superuser)
def god_mode_dashboard(request):
    """Hub central para ferramentas de admin."""
    return render(request, 'admin/god_mode.html')

@user_passes_test(is_superuser)
def merge_games_tool(request):
    if request.method == 'POST':
        form = GameMergeForm(request.POST)
        if form.is_valid():
            source = form.cleaned_data['source_game']
            target = form.cleaned_data['target_game']
            
            try:
                # ATOMICIDADE: Ou faz tudo, ou não faz nada.
                with transaction.atomic():
                    _perform_merge(request, source, target)
                    
                messages.success(request, f"SUCESSO: '{source.title}' foi fundido em '{target.title}'.")
                return redirect('god_mode_dashboard')
                
            except Exception as e:
                messages.error(request, f"ERRO CRÍTICO NO MERGE: {str(e)}")
    else:
        form = GameMergeForm()

    return render(request, 'admin/merge_tool.html', {'form': form})

def _perform_merge(request, source, target):
    """
    Lógica Cirúrgica de Merge:
    1. Move PlatformGames (Links Steam/PSN)
    2. Funde LibraryEntries (Playtime e Status)
    3. Re-aponta Reviews, Dicas e Listas
    4. Deleta o Source
    """
    # 1. Platform Games (O elo entre MasterGame e o mundo externo)
    source_pgs = PlatformGame.objects.filter(master_game=source)
    
    for spg in source_pgs:
        # Verifica se o Target já tem essa plataforma (Ex: Ambos tem link Steam?)
        target_pg = PlatformGame.objects.filter(master_game=target, platform=spg.platform).first()
        
        if target_pg:
            # CONFLITO: Ambos tem link na mesma plataforma.
            # Ação: Migrar users do SPG para o TPG e deletar SPG.
            _migrate_users_between_platforms(spg, target_pg)
            spg.delete()
        else:
            # SEM CONFLITO: Apenas aponta o link para o novo mestre
            spg.master_game = target
            spg.save()

    # 2. Dicas e Listas (Links diretos com MasterGame)
    GameTip.objects.filter(master_game=source).update(master_game=target)
    
    # Listas: Evitar duplicatas (User ter o mesmo jogo 2x na lista)
    source_list_items = GameListItem.objects.filter(master_game=source)
    for item in source_list_items:
        if not GameListItem.objects.filter(game_list=item.game_list, master_game=target).exists():
            item.master_game = target
            item.save()
        else:
            item.delete() # Já tem na lista, remove a duplicata

    # 3. Fim: Tchau Source
    source.delete()

def _migrate_users_between_platforms(source_pg, target_pg):
    """
    Move LibraryEntries e Reviews de um PG antigo para um novo.
    """
    source_entries = UserLibraryEntry.objects.filter(platform_game=source_pg)
    
    for entry in source_entries:
        # User já tem o jogo target?
        existing_target_entry = UserLibraryEntry.objects.filter(
            user=entry.user, platform_game=target_pg
        ).first()
        
        if existing_target_entry:
            # MERGE DE DADOS: Preserva o melhor dos dois mundos
            existing_target_entry.playtime_minutes = max(
                existing_target_entry.playtime_minutes, entry.playtime_minutes
            )
            
            # Hierarquia de Status: Completed > Playing > Backlog
            status_weight = {'completed': 4, 'playing': 3, 'dropped': 2, 'backlog': 1}
            if status_weight.get(entry.status, 0) > status_weight.get(existing_target_entry.status, 0):
                existing_target_entry.status = entry.status
            
            # Rating: Se o target não tem nota e o source tem, usa do source
            if not existing_target_entry.rating and entry.rating:
                existing_target_entry.rating = entry.rating
                
            existing_target_entry.save()
            
            # Move Reviews para o entry sobrevivente
            Review.objects.filter(library_entry=entry).update(library_entry=existing_target_entry)
            
            # Deleta o entry antigo
            entry.delete()
        else:
            # Caminho feliz: Só muda o apontamento
            entry.platform_game = target_pg
            entry.save()
