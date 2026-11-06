#!/usr/bin/env python3
"""Unofficial low-rate Cosmic Values cache.

Backward compatible:
  items: existing RAP values
  trading_values: listed trading values (not RAP)

Only consume public pages if permitted by the website's terms.
"""
import json, os, re, time, threading, urllib.request, urllib.parse, logging, hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from bs4 import BeautifulSoup

SOURCE=os.getenv('CV_SOURCE_URL','https://petsimulatorvalues.com/valuesnew.php?category=all')
CACHE=Path(os.getenv('CV_CACHE','cv_rap_cache.json'))
PORT=int(os.getenv('PORT','8080'))
UPDATE_SECONDS=max(900,int(os.getenv('CV_UPDATE_SECONDS','1800')))
MAX_PAGES=max(1,min(160,int(os.getenv('CV_MAX_PAGES','160'))))
DELAY_SECONDS=max(2.0,float(os.getenv('CV_PAGE_DELAY','2.0')))
USER_AGENT='PS99-Trade-Cache/2.0 (personal project; low-rate public page fetch)'
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
state_lock=threading.Lock()
state={'updated_at':0,'source':'Cosmic Values public website (unofficial)', 'items':{}, 'trading_values':{}, 'status':'no_data'}
number_rx=re.compile(r'(?<!\w)([\d,]+(?:\.\d+)?)\s*([KMBTQq]?)\b',re.I)
rap_rx=re.compile(r'\bRAP\s*:?\s*([\d,]+(?:\.\d+)?)\s*([KMBTQq]?)\b',re.I)
rarity_rx=re.compile(r'\b(?:gargantuan|titanic|huge)\b',re.I)
variant_rx=re.compile(r'\b(normal|golden|rainbow|shiny golden|shiny rainbow|golden shiny|rainbow shiny|shiny)\b',re.I)
change_rx=re.compile(r'\s*[▲▼=].*$',re.S)

def number(text):
 m=number_rx.search(str(text or ''))
 if not m:return None
 try:
  return int(float(m.group(1).replace(',',''))*{'':1,'k':1e3,'m':1e6,'b':1e9,'t':1e12,'q':1e15}[m.group(2).lower()])
 except (KeyError, ValueError, OverflowError):return None

def variant_key(title,variant):
 title=re.sub(r'\s+',' ',str(title or '').strip().lower())
 variant=re.sub(r'\s+',' ',str(variant or '').strip().lower())
 for prefix in ['shiny rainbow','rainbow shiny','shiny golden','golden shiny','rainbow','golden','shiny']:
  if title.startswith(prefix+' '):
   title=title[len(prefix)+1:]
   if variant in ('','normal'):variant=prefix
   break
 variant={'normal':'','shiny golden':'golden shiny','shiny rainbow':'rainbow shiny'}.get(variant,variant)
 return (variant+'|' if variant else '')+title

def identify_card(text,node):
 """Extract title, variant, trade amount from the same card, without using its RAP amount."""
 head=rap_rx.split(text,maxsplit=1)[0].strip() if rap_rx.search(text) else text
 title=node.get('data-name') or node.get('data-pet-name') or ''
 variant=node.get('data-variant') or ''
 # The site often renders 'Gargantuan X Normal 215B ▲ 5B ... Exist ... RAP 225B'.
 # Anchor the title to the rarity word, and the trade amount to the first variant/value pair.
 start=rarity_rx.search(head)
 if not start and not title:return None
 if start:
  prefix=head[:start.start()].strip().lower().split()
  leading=prefix[-1] if prefix and prefix[-1] in ('golden','rainbow','shiny') else ''
  payload=head[start.start():]
  vm=variant_rx.search(payload)
  if vm:
   raw_title=payload[:vm.start()].strip()
   v=vm.group(1).lower()
   if not variant:variant=v
   remainder=payload[vm.end():]
  else:
   # Only accept an explicit title + value when a variant label is unavailable.
   value_match=number_rx.search(payload)
   if not value_match:return None
   raw_title=payload[:value_match.start()].strip()
   remainder=payload[value_match.start():]
  if not title:title=(leading+' ' if leading else '')+raw_title
 else:
  remainder=head
 # Must read the *first* amount immediately following the variant label / title.
 # Other numbers in a card include trend, existence count and RAP.
 leading_amount=re.match(r'^\s*([\d,]+(?:\.\d+)?\s*[KMBTQq]?)\b',remainder,re.I)
 if not leading_amount:return None
 trading=number(leading_amount.group(1))
 if trading is None or trading<=0:return None
 key=variant_key(title,variant)
 if not re.match(r'^(?:(?:golden|rainbow|shiny|golden shiny|rainbow shiny)\|)?(?:gargantuan|titanic|huge)\s',key):return None
 return key,trading

def parse_html(html):
 soup=BeautifulSoup(html,'html.parser')
 rap={};trading={}
 # A card may be an <a> containing the whole listing; ignore parent wrappers that
 # include multiple listings by limiting text and requiring a local name + price.
 for node in soup.select('a, article, .pet-card, .value-card, .item-card, [data-name]'):
  text=' '.join(node.stripped_strings)
  if not 10<len(text)<550:continue
  identified=identify_card(text,node)
  if not identified:continue
  key,trade_price=identified
  trading[key]=trade_price
  m=rap_rx.search(text)
  if m:
   rap_price=number(m.group(1)+m.group(2))
   if rap_price and rap_price>0:rap[key]=rap_price
 return rap,trading

def fetch(url):
 request=urllib.request.Request(url,headers={'User-Agent':USER_AGENT,'Accept':'text/html'})
 with urllib.request.urlopen(request,timeout=25) as response:
  if response.status!=200:raise RuntimeError('HTTP '+str(response.status))
  return response.read(6_000_000).decode('utf-8','replace')

def refresh():
 rap_all={};trading_all={};seen=set()
 for page in range(1,MAX_PAGES+1):
  sep='&' if '?' in SOURCE else '?'
  try:html=fetch(SOURCE+sep+'page='+str(page))
  except Exception as exc:
   if page==1:raise
   logging.warning('CV page %d failed: %s',page,exc)
   break
  rap,trade=parse_html(html)
  digest=hashlib.sha256(json.dumps(trade,sort_keys=True).encode()).hexdigest()
  if digest in seen or not trade:break
  seen.add(digest)
  rap_all.update(rap);trading_all.update(trade)
  logging.info('CV page %d: RAP=%d trade=%d (total trade=%d)',page,len(rap),len(trade),len(trading_all))
  if page<MAX_PAGES:time.sleep(DELAY_SECONDS)
 if not trading_all:raise RuntimeError('No trustworthy trading-value cards parsed; retaining cache')
 with state_lock:
  state.update({'updated_at':int(time.time()),'items':rap_all,'trading_values':trading_all,'status':'ok'})
  saved=state.copy()
 CACHE.write_text(json.dumps(saved,separators=(',',':')),encoding='utf-8')
 return len(trading_all)

def loop():
 while True:
  try:logging.info('Refreshed %d trading values',refresh())
  except Exception as exc:logging.error('Refresh failed, keeping last good cache: %s',exc)
  time.sleep(UPDATE_SECONDS)

class Handler(BaseHTTPRequestHandler):
 def do_GET(self):
  endpoint=urllib.parse.urlsplit(self.path).path
  if endpoint not in ('/api/rap','/health'):
   self.send_error(404);return
  with state_lock:snapshot=state.copy()
  if endpoint=='/health':
   payload={'status':snapshot['status'],'updated_at':snapshot['updated_at'],
    'rap_count':len(snapshot['items']),'trading_count':len(snapshot['trading_values'])}
  else:payload=snapshot
  body=json.dumps(payload,separators=(',',':')).encode('utf-8')
  self.send_response(200 if snapshot['trading_values'] else 503)
  self.send_header('Content-Type','application/json')
  self.send_header('Cache-Control','public,max-age=240')
  self.send_header('Content-Length',str(len(body)))
  self.end_headers();self.wfile.write(body)

if __name__=='__main__':
 if CACHE.exists():
  try:
   previous=json.loads(CACHE.read_text('utf-8'))
   if isinstance(previous.get('trading_values'),dict) and previous['trading_values']:
    state.update(previous)
  except Exception:pass
 threading.Thread(target=loop,daemon=True).start()
 logging.info('Serving on port %d',PORT)
 ThreadingHTTPServer(('0.0.0.0',PORT),Handler).serve_forever()
