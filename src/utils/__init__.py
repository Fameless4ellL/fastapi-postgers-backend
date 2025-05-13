from datetime import datetime
from functools import wraps
from typing import Optional


class FuncRegister:
    """
    register functions for worker
    """
    __slots__ = ('__dict__',)
    WORKER_TASK_KEY = "WORKER:tasks"

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

    @staticmethod
    def deposit(history_id: int, change_type: str = 'jackpot', counter: int = 0):
        """
        See the related method for more details:
        utils/workers/transaction.py
        """

    @staticmethod
    def withdraw(history_id: int, counter: int = 0):
        """
        See the related method for more details:
        utils/workers/transaction.py
        """

    @staticmethod
    def calculate_metrics(date: Optional[datetime] = None):
        """
        See the related method for more details:
        utils/workers/cron.py
        """

    @staticmethod
    def proceed_game(game_id=None):
        """
        See the related method for more details:
        utils/workers/games.py
        """


worker = FuncRegister()


from .signature import *  # noqa
from .workers import *  # noqa
