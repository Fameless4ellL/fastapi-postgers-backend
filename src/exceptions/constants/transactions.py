""" Network constants """
from src.exceptions.schemas import ErrorMessage


OPERATION_NOT_FOUND = ErrorMessage(
    message="Operation not found",
    code_error="OperationNotFound"
)
OPERATION_IS_FINISHED = ErrorMessage(
    message="Operation already finished",
    code_error="OperationIsFinished"
)
BALANCE_NOT_FOUND = ErrorMessage(
    message="Balance not found",
    code_error="BalanceNotFound"
)
