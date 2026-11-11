"""カルカソンヌ（基本セット・2人対戦）AI研究用パッケージ。"""

from ._numba_cache import clear_if_stale

clear_if_stale()  # Numba の古いキャッシュを、どのモジュールを読むより先に片付ける

from .state import Move, State
from .tiles import load_tileset

__all__ = ["Move", "State", "load_tileset"]
