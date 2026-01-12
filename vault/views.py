from django.shortcuts import render
from .models import UserLibraryEntry

def library_view(request):
    # Removido o filtro de capa. Mostra TUDO.
    library = UserLibraryEntry.objects.select_related(
        'platform_game__master_game', 
        'platform_game__platform'
    ).filter(user=request.user).order_by('-last_played')

    context = {
        'library': library,
        'total_games': library.count()
    }
    return render(request, 'library.html', context)