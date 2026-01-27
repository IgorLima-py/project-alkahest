from django import forms
from .models import Review, UserLibraryEntry, GameTip, Platform

# ==============================================================================
# FORMULÁRIO DE REVIEW
# Melhoria: Adicionado widgets para DatePicker e Bootstrap classes
# ==============================================================================
class ReviewForm(forms.ModelForm):
    class Meta:
        model = Review
        fields = [
            'rating', 'text', 'is_recommended', 'contains_spoilers', 
            'is_replay', 'tags', 'date_started', 'date_finished'
        ]
        widgets = {
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Escreva sua análise markdown aqui...'}),
            'tags': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: rpg, difícil, masterpiece'}),
            'rating': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '5'}),
            # UX: type='date' ativa o calendário nativo do navegador
            'date_started': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_finished': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_recommended': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'contains_spoilers': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_replay': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

# ==============================================================================
# FORMULÁRIO DE EDIÇÃO DE JOGO NA BIBLIOTECA
# Melhoria: Inclui Rating e Favorito, que são essenciais ao editar
# ==============================================================================
class UserLibraryEntryForm(forms.ModelForm):
    # Dropdown de plataformas ordenado por nome
    platform = forms.ModelChoiceField(
        queryset=Platform.objects.all().order_by('name'), 
        label="Plataforma",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = UserLibraryEntry
        fields = ['platform', 'status', 'rating', 'is_favorite']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'rating': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.1', 'min': '0', 'max': '5'}),
            'is_favorite': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Pré-seleciona a plataforma atual para evitar erro de UX
            self.fields['platform'].initial = self.instance.platform_game.platform

# ==============================================================================
# FORMULÁRIO DE DICA
# Melhoria: Limitador de caracteres visual
# ==============================================================================
class GameTipForm(forms.ModelForm):
    class Meta:
        model = GameTip
        fields = ['text', 'related_achievement_name']
        widgets = {
            'text': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 2, 
                'maxlength': '280', 
                'placeholder': 'Deixe uma dica curta...'
            }),
            'related_achievement_name': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': 'Nome da conquista relacionada (opcional)'
            }),
        }