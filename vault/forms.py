import nh3
from django import forms
from .models import Review, UserLibraryEntry, GameTip, Platform, UserProfile

# --- MIXIN DE SEGURANÇA (NH3) ---
class Nh3SanitizedMixin:
    """Remove tags perigosas (<script>, onmouseover, etc) automaticamente."""
    def clean_text(self):
        data = self.cleaned_data.get('text')
        if data:
            # Configuração estrita estilo "Letterboxd"
            allowed_tags = {'b', 'i', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li', 'blockquote', 'code'}
            return nh3.clean(data, tags=allowed_tags)
        return data

    def clean_bio(self):
        data = self.cleaned_data.get('bio')
        if data:
            return nh3.clean(data, tags={'b', 'i', 'em', 'strong'}) # Bio mais restrita
        return data

# --- FORMS ---

class ReviewForm(Nh3SanitizedMixin, forms.ModelForm):
    class Meta:
        model = Review
        fields = ['rating', 'text', 'is_recommended', 'contains_spoilers', 'is_replay', 'tags', 'date_started', 'date_finished']
        widgets = {
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Markdown suportado (HTML perigoso será removido)...'}),
            'rating': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '0', 'max': '5'}),
            'date_started': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_finished': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_recommended': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'contains_spoilers': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_replay': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tags': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    # O Mixin já cuida do clean_text, mas precisamos chamar explicitamente se o campo não chamar clean_<field>
    def clean(self):
        cleaned_data = super().clean()
        if 'text' in cleaned_data:
            cleaned_data['text'] = nh3.clean(cleaned_data['text'], tags={'b', 'i', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li'})
        return cleaned_data

class GameTipForm(forms.ModelForm):
    class Meta:
        model = GameTip
        fields = ['text', 'related_achievement_name']
        widgets = {
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'maxlength': '280'}),
            'related_achievement_name': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    def clean_text(self):
        data = self.cleaned_data.get('text')
        # Tips não permitem HTML nenhum, apenas texto puro sanitizado
        return nh3.clean(data, tags=set()) 

class UserLibraryEntryForm(forms.ModelForm):
    platform = forms.ModelChoiceField(queryset=Platform.objects.all().order_by('name'), widget=forms.Select(attrs={'class': 'form-select'}))
    class Meta:
        model = UserLibraryEntry
        fields = ['platform', 'status', 'rating', 'is_favorite']
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'rating': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.5', 'min': '0', 'max': '5'}),
            'is_favorite': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
