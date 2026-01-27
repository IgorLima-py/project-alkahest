from django import forms
from .models import Review, UserLibraryEntry, GameTip, Platform

class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'text', 'is_recommended', 'contains_spoilers', 'tags', 'date_started', 'date_finished']

# --- NOVO FORM PARA EDITAR ENTRADA DA BIBLIOTECA ---
class UserLibraryEntryForm(forms.ModelForm):
    # Permite que o usuário escolha uma nova plataforma na lista
    platform = forms.ModelChoiceField(queryset=Platform.objects.all().order_by('name'))

    class Meta:
        model = UserLibraryEntry
        fields = ['platform', 'status']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Pré-seleciona a plataforma atual do jogo
            self.fields['platform'].initial = self.instance.platform_game.platform

# --- NOVO FORM PARA EDITAR DICA ---
class GameTipForm(forms.ModelForm):
    class Meta:
        model = GameTip
        fields = ['text']