# game_24/__init__.py
"""24 点游戏包的入口：只导出蓝图，路由细节在 routes.py。"""
from .routes import bp

__all__ = ['bp']
