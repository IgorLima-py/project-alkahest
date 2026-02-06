import pytest
from django.utils.translation import activate, gettext as _
from django.db import connection

@pytest.mark.django_db
class TestInfraAndLocalization:

    def test_database_extensions_active(self):
        """
        ARQUITETURA: Verifica se a migration 0002 funcionou e
        as extensões pg_trgm e unaccent estão ativas no banco de teste.
        """
        with connection.cursor() as cursor:
            # Comando SQL para listar extensões ativas
            cursor.execute("SELECT extname FROM pg_extension;")
            extensions = [row[0] for row in cursor.fetchall()]
            
        assert 'pg_trgm' in extensions, "CRÍTICO: Extensão pg_trgm hiante. Busca vai quebrar."
        assert 'unaccent' in extensions, "CRÍTICO: Extensão unaccent ausente. Busca PT-BR vai falhar."

    def test_translation_machinery(self):
        """
        I18N: Verifica se o Django consegue trocar de idioma dinamicamente.
        Não testa o template, mas sim se o sistema de tradução carregou.
        """
        # 1. Ativa Inglês
        activate('en-us')
        # Dicionário padrão do Django para admin/auth
        text_en = _("Log in") 
        
        # 2. Ativa Português
        activate('pt-br')
        text_pt = _("Log in")

        # 3. Verifica se houve mudança (Django já traz 'Log in' traduzido nativamente como 'Acessar' ou 'Entrar')
        # Nota: Se falhar, pode ser que 'Log in' não tenha tradução exata carregada, 
        # mas serve para testar se o objeto de tradução mudou.
        
        # Teste mais confiável: Erros de formulário (já embutidos no Django)
        from django.core.exceptions import ValidationError
        from django import forms
        
        class DummyForm(forms.Form):
            name = forms.CharField(required=True)

        # Form vazio em PT-BR
        activate('pt-br')
        f_pt = DummyForm(data={})
        f_pt.is_valid()
        msg_pt = f_pt.errors['name'][0]
        
        # Form vazio em EN
        activate('en')
        f_en = DummyForm(data={})
        f_en.is_valid()
        msg_en = f_en.errors['name'][0]

        assert msg_pt != msg_en
        assert "obrigatório" in msg_pt or "preenchido" in msg_pt
        assert "required" in msg_en

