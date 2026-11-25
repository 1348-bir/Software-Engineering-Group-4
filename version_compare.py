"""Compare normalized source trees using the shared statistics engine."""
from code_stats import analyze_uploads, FIELDS


def index_files(report, strip_root):
    pairs = []
    for row in report['files']:
        parts = row['name'].replace('\\', '/').split('/')
        if len(parts) > 1 and parts[0].lower().endswith('.zip'):
            parts = parts[1:]
        pairs.append((parts, row))
    remove = (strip_root and pairs and all(len(p) > 1 for p, _ in pairs)
              and len({p[0] for p, _ in pairs}) == 1)
    result = {}
    for parts, row in pairs:
        name = '/'.join(parts[1:] if remove else parts)
        if name in result:
            raise ValueError('路径规范化后出现同名文件：' + name + '；请分别上传一个项目版本')
        result[name] = row
    return result


def compare_uploads(before, after, strip_root=True):
    old, new = analyze_uploads(before), analyze_uploads(after)
    left, right = index_files(old, strip_root), index_files(new, strip_root)
    rows = []
    counts = dict(added=0, deleted=0, modified=0, unchanged=0)
    for name in sorted(left.keys() | right.keys()):
        a, b = left.get(name), right.get(name)
        status = 'added' if a is None else 'deleted' if b is None else (
            'unchanged' if a['content_hash'] == b['content_hash'] and a['language'] == b['language'] else 'modified')
        counts[status] += 1
        delta = {k: (b[k] if b else 0) - (a[k] if a else 0) for k in FIELDS}
        reliable = all(r is None or (r['function_supported'] and not r['function_warning']) for r in (a, b))
        delta['functions'] = ((b['functions'] if b else 0) - (a['functions'] if a else 0)) if reliable else None
        rows.append(dict(name=name, status=status, before=a, after=b, delta=delta))
    return dict(files=rows, counts=counts, before=old, after=new,
        delta={k: new['totals'][k] - old['totals'][k] for k in (*FIELDS, 'files')})
