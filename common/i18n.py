"""Shared language selection and forgiving message formatting."""


def select_language(request, translations):
    lang = request.args.get('lang')
    if lang in translations:
        return lang
    accepted = request.headers.get('Accept-Language', '')
    if 'zh' in accepted:
        return 'zh'
    if 'ja' in accepted:
        return 'ja'
    return 'en'


def translate(translations, key, lang='zh', **kwargs):
    text = translations.get(lang, translations['zh']).get(key, key)
    if kwargs:
        try:
            return text.format(**kwargs)
        except Exception:
            return text
    return text


def bind_translator(translate_message, lang):
    return lambda key, **kwargs: translate_message(key, lang, **kwargs)
