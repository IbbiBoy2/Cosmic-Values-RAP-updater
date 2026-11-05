#!/usr/bin/env python3
"""CV RAP updater & minimal HTTPS-ready JSON API. Python stdlib + beautifulsoup4.

Public HTML only. Do not use if site terms prohibit automated collection.
No claim of an official CV API. Cache survives site outages.
"""
import json, os, re, time, threading, urllib.request, urllib.parse, logging, hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from bs4 import BeautifulSoup

SOURCE = os.getenv('CV_SOURCE_URL', 'https://petsimulatorvalues.com/valuesnew.php?category=all')
CACHE = Path(os.getenv('CV_CACHE', 'cv_rap_cache.json'))
PORT = int(os.getenv('PORT', '8080'))
UPDATE_SECONDS = max(900, int(os.getenv('CV_UPDATE_SECONDS', '1800')))
MAX_PAGES = max(1, min(160, int(os.getenv('CV_MAX_PAGES', '160'))))
DELAY_SECONDS = max(2.0, float(os.getenv('CV_PAGE_DELAY', '2.0')))
USER_AGENT = 'PS99-RAP-Cache/1.0 (personal game, low-rate public page fetch)'
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
state_lock=threading.Lock()
state={'updated_at':0,'source':'Cosmic Values public website (unofficial)', 'items':{}, 'status':'no_data'}
number_rx=re.compile(r'([\d,.]+)\s*([KMBTQq]?)\b',re.I)
rap_rx=re.compile(r'\bRAP\s*:?\s*([\d,.]+)\s*([KMBTQq]?)\b',re.I)

def number(text):
 m=number_rx.search(str(text or ''))
 if not m:return None
 try: return int(float(m.group(1).replace(',','')) * {'':1,'k':1e3,'m':1e6,'b':1e9,'t':1e12,'q':1e15}[m.group(2).lower()])
 except (KeyError,ValueError):return None

def normalize(name):
 name=re.sub(r'\s+',' ',str(name or '').strip().lower())
 name=re.sub(r'^normal\s+','',name)
 return name

def variant_key(title, variant):
 # E.g. "Golden Huge Cat" becomes "golden|huge cat".
 title=normalize(title); variant=normalize(variant)
 for prefix in ['shiny rainbow','rainbow shiny','shiny golden','golden shiny','rainbow','golden','shiny']:
  if title.startswith(prefix+' '):
   title=title[len(prefix)+1:]
   if not variant or variant=='normal':variant=prefix
   break
 variant={'normal':'','shiny golden':'golden shiny','shiny rainbow':'rainbow shiny'}.get(variant,variant)
 return (variant+'|' if variant else '')+title

def parse_html(html):
 soup=BeautifulSoup(html,'html.parser')
 prices={}
 # CV's current site uses repeated card/list entries. We never infer values from generic whole-page text.
 for node in soup.select('a, article, .pet-card, .value-card, .item-card, [data-name]'):
  text=' '.join(node.stripped_strings)
  if len(text)>550 or not rap_rx.search(text):continue
  m=rap_rx.search(text)
  if not m:continue
  value=number(m.group(1)+m.group(2))
  if not value or value<=0:continue
  # Item name must come from explicit data/title OR card text before its "Variant" label.
  title=node.get('data-name') or node.get('data-pet-name') or ''
  variant=node.get('data-variant') or ''
  if not title:
   # The newer site displays: "Huge Cat Normal 11.5B ... Exist ... RAP 13.72B".
   head=text[:m.start()].strip()
   # Remove category labels and start only at recognizable pet rarity.
   rarity=re.search(r'\b(?:Golden|Rainbow|Shiny)?\s*(?:Gargantuan|Titanic|Huge)\s+[A-Za-z0-9][A-Za-z0-9\-\s]{1,95}',head,re.I)
   if rarity:
    guess=rarity.group().strip()
    guess=re.split(r'\s+(?:Normal|Golden|Rainbow|Shiny)\b',guess,maxsplit=1,flags=re.I)[0]
    # Numerical end of description excludes sale price/ages.
    guess=re.split(r'\s+\d+(?:[.,]\d+)?[KMBTQ]?\b',guess,maxsplit=1)[0].strip()
    title=guess
   # Older page anchors have title attribute, with RAP in text.
   if not title: title=node.get('title','')
  if not title:continue
  if not variant:
   vm=re.search(r'\bVariant\s+(Normal|Golden|Rainbow|Shiny Golden|Shiny Rainbow|Shiny)\b',text,re.I)
   if vm:variant=vm.group(1)
  key=variant_key(title,variant)
  if not re.match(r'^(?:(?:golden|rainbow|shiny|golden shiny|rainbow shiny)\|)?(?:gargantuan|titanic|huge)\s',key):continue
  prices[key]=value
 return prices

def fetch(url):
 req=urllib.request.Request(url, headers={'User-Agent': USER_AGENT, 'Accept': 'text/html'})
 with urllib.request.urlopen(req,timeout=25) as resp:
  if resp.status!=200:raise RuntimeError('HTTP '+str(resp.status))
  return resp.read(6_000_000).decode('utf-8','replace')

def refresh():
 all_prices={};seen_hashes=set();last_count=0
 for page in range(1,MAX_PAGES+1):
  sep='&' if '?' in SOURCE else '?'
  url=SOURCE+(sep+'page='+str(page))
  try:content=fetch(url)
  except Exception as ex:
   if page==1:raise
   logging.warning('CV page %d failed: %s',page,ex);break
  parsed=parse_html(content)
  sig=hashlib.sha256(json.dumps(parsed,sort_keys=True).encode()).hexdigest()
  if sig in seen_hashes or not parsed:break
  seen_hashes.add(sig);all_prices.update(parsed)
  logging.info('CV page %d: %d values, accumulated %d',page,len(parsed),len(all_prices))
  if page<MAX_PAGES:time.sleep(DELAY_SECONDS)
 if not all_prices: raise RuntimeError('No trustworthy item cards parsed; retaining old cache')
 with state_lock:
  state.update({'updated_at':int(time.time()),'items':all_prices,'status':'ok'})
 CACHE.write_text(json.dumps(state,separators=(',',':')),encoding='utf-8')
 return len(all_prices)

def loop():
 while True:
  try:logging.info('Refreshed %d prices',refresh())
  except Exception as ex:logging.error('Refresh failed, keeping last good cache: %s',ex)
  time.sleep(UPDATE_SECONDS)

class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  if urllib.parse.urlsplit(self.path).path not in ('/api/rap','/health'):
   self.send_error(404);return
  with state_lock: snapshot=state.copy()
  if self.path.startswith('/health'):
   payload={'status':snapshot['status'],'updated_at':snapshot['updated_at'],'count':len(snapshot['items'])}
  else:payload=snapshot
  body=json.dumps(payload,separators=(',',':')).encode()
  self.send_response(200 if snapshot['items'] else 503)
  self.send_header('Content-Type','application/json')
  self.send_header('Cache-Control','public,max-age=240')
  self.send_header('Content-Length',str(len(body)))
  self.end_headers();self.wfile.write(body)

if __name__=='__main__':
 if CACHE.exists():
  try:
   old=json.loads(CACHE.read_text('utf-8'))
   if isinstance(old.get('items'),dict):state.update(old)
  except Exception:pass
 threading.Thread(target=loop,daemon=True).start()
 logging.info('Serving on port %d. Deploy behind HTTPS for Roblox HttpService.',PORT)
 ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
