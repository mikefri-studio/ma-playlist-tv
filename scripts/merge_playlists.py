import os
import re
import requests
from datetime import datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

os.makedirs('output', exist_ok=True)

class Merger:
    def __init__(self):
        self.sources, self.channels = [], {}
        self.broken = []
        self.timeout = 15

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
            return "id:" + ch['id'].lower()
        clean = re.sub(r'\s+', ' ', ch['name'].lower().strip())
        return "name:" + clean

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

    # ====== NOUVEAU : test des flux ======
    def check_stream(self, ch):
        """Teste si un flux est accessible. Retourne (channel, ok, reason)"""
        url = ch['url']
        try:
            # D'abord un HEAD (rapide)
            r = requests.head(url, timeout=self.timeout,
                             headers={'User-Agent': 'Mozilla/5.0'},
                             allow_redirects=True)
            # Si HEAD ne marche pas, essayer un GET limité
            if r.status_code >= 400:
                r = requests.get(url, timeout=self.timeout,
                                headers={'User-Agent': 'Mozilla/5.0'},
                                stream=True)
                # Ne pas télécharger tout le flux, juste vérifier
                r.close()
            if r.status_code >= 400:
                return ch, False, f"HTTP {r.status_code}"
            # Vérifier le Content-Type (doit être vidéo ou m3u8)
            ct = r.headers.get('content-type', '').lower()
            valid_ct = any(x in ct for x in ['video', 'mpegurl', 'application/vnd.apple.mpegurl', 'octet-stream'])
            if not valid_ct and ct:
                # Certains serveurs ne renvoient pas de CT correct, on accepte quand même
                pass
            return ch, True, "OK"
        except requests.exceptions.Timeout:
            return ch, False, "Timeout"
        except requests.exceptions.ConnectionError:
            return ch, False, "Connexion refusée"
        except Exception as e:
            return ch, False, str(e)[:50]

    def verify_streams(self):
        """Teste tous les flux en parallèle"""
        print(f"\n=== TEST DES {len(self.channels)} FLUX ===")
        valid = {}
        items = list(self.channels.items())
        
        with ThreadPoolExecutor(max_workers=25) as executor:
            futures = {executor.submit(self.check_stream, ch): k for k, ch in items}
            done = 0
            for future in as_completed(futures):
                ch, ok, reason = future.result()
                k = futures[future]
                done += 1
                status = "OK" if ok else "KO"
                print(f"[{done}/{len(items)}] {status} {ch['name'][:30]:30} {reason if not ok else ''}")
                if ok:
                    valid[k] = ch
                else:
                    self.broken.append({
                        'name': ch['name'],
                        'url': ch['url'],
                        'reason': reason
                    })
        
        print(f"\n=== RESULTAT ===")
        print(f"✅ Flux OK: {len(valid)}")
        print(f"❌ Flux HS: {len(self.broken)}")
        self.channels = valid

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
        
        # Sauvegarder aussi la liste des flux cassés
        if self.broken:
            with open('output/broken.txt', 'w', encoding='utf-8') as f:
                f.write(f"# Flux cassés ({len(self.broken)})\n")
                f.write(f"# Date: {datetime.now().isoformat()}\n\n")
                for b in self.broken:
                    f.write(f"# {b['reason']}\n{b['name']} - {b['url']}\n")
            print(f"Broken: {len(self.broken)} flux -> output/broken.txt")

    def run(self):
        self.load()
        all_ch = []
        for s in self.sources:
            c = self.download(s)
            if c:
                all_ch.extend(self.parse(c))
        self.merge(all_ch)
        self.verify_streams()  # <-- LE TEST DES FLUX
        self.generate()
        print("\nDone!")

if __name__ == '__main__':
    Merger().run()