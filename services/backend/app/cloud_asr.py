"""Shared consent policy for explicitly selected cloud ASR adapters."""
from urllib.parse import urlsplit

CLOUD_BACKENDS = {'relay', 'groq', 'paraformer'}


def adapter(settings):
    if settings.stt_backend == 'paraformer':
        from . import paraformer_asr
        return paraformer_asr
    if settings.stt_backend == 'groq':
        from . import groq_asr
        return groq_asr
    from . import relay_asr
    return relay_asr


def cloud_policy(settings):
    return adapter(settings).cloud_policy(settings)


def configured(settings):
    return adapter(settings).configured(settings)


def destination(settings):
    if settings.stt_backend == 'paraformer':
        from .paraformer_asr import MODEL
        return {'model': MODEL, 'host': urlsplit(settings.paraformer_base_url).hostname}
    if settings.stt_backend == 'groq':
        from .groq_asr import ENDPOINT
        return {'model': settings.groq_asr_model, 'host': urlsplit(ENDPOINT).hostname}
    return {'model': settings.relay_asr_model, 'host': urlsplit(settings.relay_asr_url).hostname}
