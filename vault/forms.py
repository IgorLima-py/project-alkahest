import nh3
from django import forms
from django.core.exceptions import ValidationError
from .models import Review, UserLibraryEntry, GameTip, Platform, UserProfile
from django.utils.translation import gettext_lazy as _
from .widgets import MetacriticRatingWidget

# --- MIXIN DE SEGURANÇA (NH3) ---
class Nh3SanitizedMixin:
    def clean_text(self):
        data = self.cleaned_data.get('text')
        if data:
            allowed_tags = {'b', 'i', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li', 'blockquote', 'code'}
            return nh3.clean(data, tags=allowed_tags)
        return data

    def clean_bio(self):
        data = self.cleaned_data.get('bio')
        if data:
            return nh3.clean(data, tags={'b', 'i', 'em', 'strong'})
        return data

# --- FORMS CORRIGIDOS ---

class ReviewForm(Nh3SanitizedMixin, forms.ModelForm):
    # Usamos o campo rating DIRETO, com o widget visual
    rating = forms.IntegerField(
        required=False,
        widget=MetacriticRatingWidget(), # O widget já lida com a UI de 10 barras
        label="Sua Nota"
    )

    class Meta:
        model = Review
        # 'rating' volta para os fields
        fields = ['rating', 'text', 'is_recommended', 'contains_spoilers', 'is_replay', 'tags', 'date_started', 'date_finished']
        widgets = {
            'text': forms.Textarea(attrs={'class': 'form-control', 'rows': 5, 'placeholder': 'Markdown suportado...'}),
            'date_started': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'date_finished': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_recommended': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'contains_spoilers': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_replay': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'tags': forms.TextInput(attrs={'class': 'form-control'}),
        }
    
    # O Mixin já cuida do clean_text
    def clean(self):
        cleaned_data = super().clean()
        if 'text' in cleaned_data:
            cleaned_data['text'] = nh3.clean(cleaned_data['text'], tags={'b', 'i', 'strong', 'em', 'p', 'br', 'ul', 'ol', 'li'})
        return cleaned_data

    # Save simplificado: O widget já envia 0-100, não precisa multiplicar!
    def save(self, commit=True):
        review = super().save(commit=False)
        if commit:
            review.save()
        return review


class UserLibraryEntryForm(forms.ModelForm):
    platform = forms.ModelChoiceField(queryset=Platform.objects.all().order_by('name'), widget=forms.Select(attrs={'class': 'form-select'}))
    
    # Rating direto com widget visual
    rating = forms.IntegerField(
        required=False, 
        widget=MetacriticRatingWidget()
    )

    class Meta:
        model = UserLibraryEntry
        fields = ['platform', 'status', 'rating', 'is_favorite'] # 'rating' incluso aqui
        widgets = {
            'status': forms.Select(attrs={'class': 'form-select'}),
            'is_favorite': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    # Save simplificado também
    def save(self, commit=True):
        entry = super().save(commit=False)
        if commit:
            entry.save()
        return entry


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
        return nh3.clean(data, tags=set()) 