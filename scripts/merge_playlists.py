import os
import re
import requests
from datetime import datetime
from urllib.parse import urlparse

os.makedirs('output', exist_ok=True)

class Merger:
    def __init__(self):
        self.sources, self.channels = [], {}

    def load(self):
        with open('sources.txt', 'r', encoding='utf-8-sig') as f:
            for l in f:
                l = l.strip()
                if l and not l.startswith('#'):
                    self.sources.append(l)
        print(f"Sources: {len(self.sources)}")

    def download(self, url):
        try:
            r = requests.get(url, timeout=20, headers={'User-Agent': 'Mozilla/5.0'})
            r.raise_for_status()
            print(f"OK {urlparse(url).netloc} ({len(r.text)} bytes)")
            return r.text
        except Exception as e:
            print(f"ERR {url}: {e}")
            return None

    def parse(self, content):
        chs, cur = [], None
        for l in content.split('\n'):
            l = l.strip()
            if not l:
                continue
            if l.startswith('#EXTINF'):
                n = re.search(r',(.*?)$', l)
                lg = re.search(r'tvg-logo="([^"]*)"', l)
                g = re.search(r'group-title="([^"]*)"', l)
                i = re.search(r'tvg-id="([^"]*)"', l)
                nm = re.search(r'tvg-chno="?(\d+)"?', l)
                cur = {
                    'name': n.group(1).strip() if n else 'Unknown',
                    'logo': lg.group(1) if lg else '',
                    'group': g.group(1) if g else 'Autres',
                    'id': i.group(1) if i else '',
                    'num': int(nm.group(1)) if nm else 0,
                    'url': ''
                }
            elif not l.startswith('#') and cur:
                cur['url'] = l
                if cur['url'].startswith('http'):
                    chs.append(cur)
                cur = None
        return chs

    def key(self, ch):
        if ch['id']:
            return f"id:{ch['id'].lower()}"
        return f"name:{re.sub(r'\s+', ' ', ch['name'].lower().strip())}"

    def merge(self, all_ch):
        for ch in all_ch:
            k = self.key(ch)
            if k not in self.channels:
                self.channels[k] = ch
            else:
                e = self.channels[k]
                if not e['logo'] and ch['logo']:
                    self.channels[k] = ch
                if not e['id'] and ch['id']:
                    self.channels[k]['id'] = ch['id']
        print(f"Chaines uniques: {len(self.channels)}")

    def generate(self):
        os.makedirs('output', exist_ok=True)
        s = sorted(self.channels.values(),
                   key=lambda x: (x['num'] if x['num'] > 0 else 9999, x['name']))
        with open('output/france-clean.m3u', 'w', encoding='utf-8') as f:
            f.write('#EXTM3U\n')
            f.write(f'# Generated: {datetime.now().isoformat()}\n')
            f.write(f'# Total: {len(s)}\n\n')
            for i, ch in enumerate(s, 1):
                e = '#EXTINF:-1'
                if ch['id']:
                    e += f' tvg-id="{ch["id"]}"'
                if ch['logo']:
                    e += f' tvg-logo="{ch["logo"]}"'
                if ch['group']:
                    e += f' group-title="{ch["group"]}"'
                e += f' tvg-chno="{i}",{ch["name"]}'
                f.write(f'{e}\n{ch["url"]}\n')
        print(f"Output: {len(s)} chaines -> output/france-clean.m3u")

    def run(self):
        self.load()
        all_ch = []
        for s in self.sources:
            c = self.download(s)
            if c:
                all_ch.extend(self.parse(c))
        self.merge(all_ch)
        self.generate()
        print("Done!")

if __name__ == '__main__':
    Merger().run()