from django.contrib import admin
from .models import MasterGame, Platform, PlatformGame, UserLibraryEntry, Achievement

# Isso aqui diz pro Django: "Crie uma tela pra eu editar essas tabelas"
admin.site.register(MasterGame)
admin.site.register(Platform)
admin.site.register(PlatformGame)
@admin.register(UserLibraryEntry)
class UserLibraryEntryAdmin(admin.ModelAdmin):
    list_display = ('get_game_title', 'status', 'playtime_hours', 'user')
    list_filter = ('status', 'platform_game__platform')
    search_fields = ('platform_game__master_game__title',)

    # Truque para pegar campos de tabelas relacionadas (JOIN)
    def get_game_title(self, obj):
        return obj.platform_game.master_game.title
    get_game_title.short_description = 'Jogo'

    def playtime_hours(self, obj):
        return f"{obj.playtime_minutes / 60:.1f} h"
    playtime_hours.short_description = 'Horas'
admin.site.register(Achievement)