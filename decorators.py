from django.http import HttpResponseBadRequest


def ajax_required(f):
    """
    Проверяет, является ли запрос AJAX-запросом.
    Если нет — возвращает ошибку 400 (Bad Request).
    """

    def wrap(request, *args, **kwargs):
        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return f(request, *args, **kwargs)
        return HttpResponseBadRequest("Этот URL доступен только через AJAX.")

    wrap.__doc__ = f.__doc__
    wrap.__name__ = f.__name__
    return wrap
