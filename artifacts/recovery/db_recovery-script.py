import sqlite3, json, re, datetime
from pathlib import Path

DB = '/home/error/.local/share/opencode/opencode.db'
PREFIX = '/home/error/Lino-Codec-work/'
OUT = Path('/home/error/Lino-Codec-work-recovered')

con = sqlite3.connect(DB)
rows = con.execute("""
select p.time_created, p.data from part p
where p.data like '%Lino-Codec-work%' and json_extract(p.data,'$.type')='tool'
order by p.time_created""").fetchall()
print('candidate parts:', len(rows))

events = {}
for t, data in rows:
    try:
        d = json.loads(data)
    except Exception:
        continue
    tool = d.get('tool')
    state = d.get('state', {})
    inp = state.get('input', {}) or {}
    fp = inp.get('filePath')
    if not isinstance(fp, str) or not fp.startswith(PREFIX):
        continue
    events.setdefault(fp, []).append((t, tool, inp, state))
print('files with events:', len(events))

def parse_read_output(out):
    if '<content>' not in out:
        return None, False
    body = out.split('<content>', 1)[1]
    body = body.rsplit('</content>', 1)[0] if '</content>' in body else body
    truncated = 'Showing lines' in out or '(Showing' in out
    lines = body.split('\n')
    result = []
    first_num = None
    for line in lines:
        m = re.match(r'^(\d+): ?(.*)$', line)
        if m:
            if first_num is None:
                first_num = int(m.group(1))
            result.append(m.group(2))
    if not result:
        return None, False
    complete = (first_num == 1) and not truncated
    return '\n'.join(result) + '\n', complete

report = []
for fp, evts in sorted(events.items()):
    rel = fp[len(PREFIX):]
    content = None
    complete = False
    source = None
    pending_note = []
    for t, tool, inp, state in evts:
        ts = datetime.datetime.fromtimestamp(t/1000).strftime('%m-%d %H:%M')
        if tool == 'write':
            content = inp.get('content', '')
            complete = True
            source = f"write@{ts}"
        elif tool == 'read':
            parsed, comp = parse_read_output(state.get('output', ''))
            if parsed and (comp or content is None):
                if comp or not complete:
                    content = parsed
                    complete = comp
                    source = f"read@{ts}{'(partial)' if not comp else ''}"
        elif tool == 'edit':
            old = inp.get('oldString', '')
            new = inp.get('newString', '')
            if content is not None and old and old in content:
                content = content.replace(old, new) if inp.get('replaceAll') else content.replace(old, new, 1)
            else:
                pending_note.append(f"edit@{ts} n/a")
    if content is None:
        continue
    target = OUT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    flag = 'FULL' if complete else 'PART'
    note = f"  ({len(pending_note)} edits n/a)" if pending_note else ''
    report.append(f"{flag}  {rel} ({len(content)} B, {source}){note}")

print('\n'.join(report))
print('files written:', len(report))
