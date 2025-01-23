from functools import wraps


class FuncRegister:
    """
    register functions for worker
    """
    __slots__ = ('__dict__',)

    @property
    def register(self):
        def wrapper(func):
            @wraps(func)
            def wrapped_func(*args, **kwargs):
                return func(*args, **kwargs)

            self.__dict__[func.__name__] = wrapped_func
            return wrapped_func

        return wrapper

    def __contains__(self, item):
        return item in self.__dict__.keys()


class Worker(FuncRegister):
    """
    register functions for cache worker
    """

    def generate_game(self) -> bool: ...
    def proceed_game(self, game_id: int) -> bool: ...