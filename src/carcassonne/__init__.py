"""カルカソンヌ（基本セット・2人対戦）AI研究用パッケージ。"""

from .state import Move, State
from .tiles import load_tileset

__all__ = ["Move", "State", "load_tileset"]
