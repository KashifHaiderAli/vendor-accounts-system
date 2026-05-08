from functools import wraps


def phase_two_allow_anonymous(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return wrapper
