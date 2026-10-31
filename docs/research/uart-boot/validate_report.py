from pathlib import Path
from html.parser import HTMLParser
import json,re,hashlib,collections,zipfile,os
P=Path(__file__).resolve().parent
coverage=json.loads((P/'coverage.json').read_text())
entries=json.loads((P/'annotations.json').read_text())
maps=[json.loads(s) for s in (P/'line-map.jsonl').read_text().splitlines()]
def split(b):
    if not b:return []
    a=b.split(b'\n');return a[:-1] if a[-1]==b'' else a
grouped=collections.defaultdict(list)
for r in maps:
    grouped[r['capture']].append(r)
    assert r['entry'] in entries
    e=entries[r['entry']]
    assert e['capture']==r['capture'] and e['first_line']<=r['line']<=e['last_line']
count=0;private_values=set()
stamp=re.compile(rb'\[\d\d:\d\d:\d\d\.\d{3}\] ?')
for c in coverage['source_files']:
    source_root=Path(os.environ.get('ROCA_UART_SOURCE', str(P.parents[2]/coverage['source_root'])))
    b=(source_root/c['file']).read_bytes()
    assert hashlib.sha256(b).hexdigest()==c['sha256']
    assert len(b)==c['bytes']
    ss=split(b);assert len(ss)==c['physical_lines']
    if c['covered']:
        ms=grouped[c['file']]
        assert [r['line'] for r in ms]==list(range(1,len(ss)+1))
        for line,m in zip(ss,ms):
            assert hashlib.sha256(line).hexdigest()==entries[m['entry']]['original_line_sha256'],(c['file'],m['line'])
        count+=len(ms)
        for v in re.findall(rb'systemd\.machine_id=([^\s]+)',stamp.sub(b'',b)):
            private_values.add(v.decode())
        normalized=stamp.sub(b'',b).decode('utf8','replace')
        normalized=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',normalized)
        for pat in (r'libcontainer container ([^\s:]+)',r'/run/docker/netns/([^\s.]+)',r'/var/lib/docker/overlay2([^\s]*?)/merged'):
            for v in re.findall(pat,normalized):
                v=v.rstrip('.')
                if len(v)>8:private_values.add(v)
assert count==coverage['covered_source_lines']
assert len(grouped['job-watch-live.reconstructed'])==coverage['derived_reconstructed_lines']
assert not any(e['classification']=='UNREVIEWED' for e in entries.values())
raw_entries=[entries[r['entry']] for r in grouped['job-watch-live.log']]
decoded_safe=b''.join(bytes.fromhex(e['text'].split(' ',1)[1]) for e in raw_entries)
for v in private_values:
    assert v.encode() not in decoded_safe
    for f in ('roca-uart-annotated.html','annotations.json','line-map.jsonl','coverage.json','README.txt'):
        assert v not in (P/f).read_text(),f
class CheckHTML(HTMLParser):
    def __init__(self):super().__init__();self.ids=[];self.links=[];self.external=[];self.scripts=[];self.entries=0
    def handle_starttag(self,t,attrs):
        a=dict(attrs)
        if 'id' in a:self.ids.append(a['id'])
        if t=='a' and a.get('href','').startswith('#') and not a.get('data-jump'):self.links.append(a['href'][1:])
        if t in ('img','script','iframe','link') and (a.get('src') or a.get('href')):self.external.append((t,a))
        if t=='article' and a.get('class')=='entry':self.entries+=1
h=CheckHTML();h.feed((P/'roca-uart-annotated.html').read_text())
assert len(h.ids)==len(set(h.ids)), 'Duplicate HTML IDs'
assert not (set(h.links)-set(h.ids)),set(h.links)-set(h.ids)
assert h.entries==len(entries)
assert not h.external,'External resources should not load automatically'
with zipfile.ZipFile(P/'roca-uart-report.zip') as z:
    assert z.testzip() is None
    assert set(z.namelist())=={'roca-uart-annotated.html','coverage.json','line-map.jsonl','annotations.json','README.txt'}
    for f in z.namelist():assert z.read(f)==(P/f).read_bytes()
result=dict(source_hashes_unchanged=True,source_lines_individually_verified=count,derived_lines=coverage['derived_reconstructed_lines'],annotation_entries=len(entries),all_line_hashes_match=True,identifier_redaction_check='passed, including reassembled hexadecimal source',html_ids_and_links='passed',automatic_external_resource_loads=0,zip_integrity='passed',visual_preview='not completed: browser policy rejected local file: URL; no workaround attempted')
(P/'validation.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
