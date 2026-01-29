import hashlib
import json
import logging
from functools import wraps
from django.core.cache import cache
from django.conf import settings

logger = logging.getLogger(__name__)

def make_cache_key(prefix, *args, **kwargs):
    """Gera uma chave única baseada nos argumentos da função."""
    # Ordena kwargs para garantir que {a:1, b:2} seja igual a {b:2, a:1}
    key_data = f"{args}:{json.dumps(kwargs, sort_keys=True)}"
    key_hash = hashlib.md5(key_data.encode('utf-8')).hexdigest()
    return f"alkahest:{prefix}:{key_hash}"

def cache_external_api(timeout=60*60*24, prefix="api"):
    """
    Decorator para cachear resultados de API. 
    Salva no Redis por 'timeout' segundos.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Se Redis não estiver configurado, roda sem cache
            if not hasattr(settings, 'CACHES'):
                return func(*args, **kwargs)

            key = make_cache_key(prefix, *args, **kwargs)
            cached_data = cache.get(key)

            if cached_data is not None:
                # logger.debug(f"CACHE HIT: {key}")
                return cached_data

            # Executa a função real
            result = func(*args, **kwargs)

            if result:  # Só salva se não for None/Vazio
                cache.set(key, result, timeout)
            
            return result
        return wrapper
    return decorator
