"""兼容入口：部分文档或旧习惯用 ``python main.py`` 启动。

它不创建第二个应用，只是复用 ``app.py`` 里已经组装好的 app 对象。
"""
import os

from app import app

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=int(os.environ.get('PORT', '5050')), debug=False)
