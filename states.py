# states.py
from aiogram.fsm.state import State, StatesGroup


class ReportStates(StatesGroup):
    waiting_for_reason = State()
