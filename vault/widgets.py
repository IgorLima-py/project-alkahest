from django import forms

class MetacriticRatingWidget(forms.NumberInput):
    template_name = 'widgets/metacritic_rating.html' # Vamos criar esse HTML abaixo
    
    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        # Garante que value seja tratado como int (ex: 4.5 vira 45 se vier do banco antigo)
        if context['widget']['value'] is None:
            context['widget']['value'] = 0
        return context

    class Media:
        css = {'all': ('css/metacritic_widget.css',)}
        js = ('js/metacritic_widget.js',)
