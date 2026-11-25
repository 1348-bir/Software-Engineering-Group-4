"""Tree-sitter 常驻子进程入口：逐行读取请求，解析后逐行写回 JSON。

原生解析崩溃时只会带走这个子进程，主服务照常运行；主进程会在下次调用时重启它。
"""
import json
import sys

from function_analysis import _parse_in_process


def main():
    for line in sys.stdin.buffer:
        try:
            request = json.loads(line.decode('utf-8'))
            ranges, warning = _parse_in_process(request['source'], request['language'])
            response = {'ranges': ranges, 'warning': warning}
        except Exception as exc:  # noqa: BLE001  单个请求失败不应影响后续请求
            response = {'ranges': None, 'warning': f'函数解析失败：{type(exc).__name__}'}
        sys.stdout.buffer.write(json.dumps(response, ensure_ascii=False).encode('utf-8') + b'\n')
        sys.stdout.buffer.flush()


if __name__ == '__main__':
    main()
