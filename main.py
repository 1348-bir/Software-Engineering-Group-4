"""兼容入口：复用 app.py 中的应用和统一启动配置。"""
from app import app, run

if __name__ == '__main__':
    run()
