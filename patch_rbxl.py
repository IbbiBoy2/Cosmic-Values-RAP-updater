#!/usr/bin/env python3
"""Patch only Arcade's price-lookup Source property in a .rbxl binary, and validate chunks."""
from pathlib import Path
import struct,lz4.block,sys
SRC=Path(sys.argv[1]) if len(sys.argv)>1 else Path('/mnt/data/PetSimulator99_Gargantuan_All16_Icons_Flying_FIXED.rbxl')
DST=Path(sys.argv[2]) if len(sys.argv)>2 else Path('/mnt/data/PetSimulator99_CV_AutoRAP_Flying_Icons.rbxl')
old=SRC.read_bytes();new=bytearray(old[:32]);pos=32;changed=False;count=0
cv_insert='''
-- Cosmic Values live price cache (UNOFFICIAL community website; update proxy required).
-- To enable live prices, change this URL to YOUR deployed HTTPS updater /api/rap address.
local CV_RAP_ENDPOINT = "https://YOUR-DEPLOYED-DOMAIN.example/api/rap"
local CV_HTTP = game:GetService('HttpService')
local CV_LOOKUP = {}
local CV_LAST_SYNC = 0
local CV_DATA_AGE_LIMIT = 86400
local function CVRequestRefresh()
 if CV_RAP_ENDPOINT:find('YOUR%-DEPLOYED%-DOMAIN') then return end
 local success, response=pcall(function()
  return CV_HTTP:GetAsync(CV_RAP_ENDPOINT, false)
 end)
 if not success then warn('[CV RAP] refresh failed; holding previously fetched values: '..tostring(response));return end
 local ok,parsed=pcall(function()return CV_HTTP:JSONDecode(response)end)
 if not ok or type(parsed)~='table' or type(parsed.items)~='table' then return end
 if type(parsed.updated_at)~='number' or parsed.updated_at < os.time()-CV_DATA_AGE_LIMIT then
  warn('[CV RAP] cache older than one day; holding previously fetched values')
  return
 end
 local nextCache={}
 for k,v in pairs(parsed.items) do
  if type(k)=='string' and type(v)=='number' and v>0 and v<1e18 then
   nextCache[k]=v
  end
 end
 if next(nextCache) then
  CV_LOOKUP=nextCache
  CV_LAST_SYNC=os.time()
  print('[CV RAP] updated '..tostring(#response)..' response bytes')
 end
end
task.spawn(function()
 while true do
  CVRequestRefresh()
  task.wait(300)
 end
end)
'''
search='local function Pet99PriceForName(baseName,variant)\n'
replacement='''local function Pet99PriceForName(baseName,variant)
 local key=Pet99NormalizeName(baseName)
 if not (key:match('^huge%s') or key:match('^titanic%s') or key:match('^gargantuan%s')) then return nil,false end
 -- CV cache is authoritative ONLY when it has valid RAP for this exact pet & variant.
 local v=string.lower(tostring(variant or ''))
 if v=='shiny golden' then v='golden shiny' elseif v=='shiny rainbow' then v='rainbow shiny' end
 local lookupKey=(v~='' and (v..'|') or '')..key
 local live=CV_LOOKUP[lookupKey]
 if type(live)=='number' and live>0 then return live,false end
 -- Missing RAP: old snapshot acts only as an estimate, never advertised as CV RAP.
 local base=CV_LOOKUP[key] or Pet99PricesSnapshot[key] or Pet99Estimate(key)
 if not base then return nil,true end
 if v~='' then
  local approximate=Pet99VariantPrices[lookupKey]
  if approximate then return approximate,true end
  return math.floor(base*(Pet99EstimatedMultipliers[v] or 1)+0.5),true
 end
 return base,true
end
'''
start_marker='local function Pet99PriceForName(baseName,variant)\n'
end_marker='local function Pet99Price(item,baseName)\n'
for ci in range(5000):
 if pos+16>len(old):break
 tag=old[pos:pos+4];comp,uncomp,res=struct.unpack_from('<III',old,pos+4);payload=old[pos+16:pos+16+(comp or uncomp)];pos+=16+(comp or uncomp)
 if tag==b'PROP':
  raw=lz4.block.decompress(payload,uncompressed_size=uncomp) if comp else payload
  length=struct.unpack_from('<I',raw,4)[0];name=raw[8:8+length]
  if name==b'Source' and struct.unpack_from('<I',raw,0)[0]==93:
   header=raw[:9+length];off=len(header);segments=[]
   while off<len(raw):
    n=struct.unpack_from('<I',raw,off)[0];off+=4
    code=raw[off:off+n];off+=n
    if b'local Pet99PricesSnapshot' in code and b'local function Pet99PriceForName' in code:
     if changed:raise RuntimeError('Duplicate target source')
     s=code.decode('utf-8');assert s.count(start_marker)==1
     i=s.index(start_marker);j=s.index(end_marker,i)
     s=s[:i]+cv_insert+'\n'+replacement+s[j:]
     s=s.replace("priceSource='Verified Pet99Prices values where available; otherwise deterministic estimated RAP (not market prices)'", "priceSource='Cosmic Values RAP (if connected); otherwise estimated RAP (not verified CV data)'")
     s=s.replace("-- Additional independently checked Pet99Prices entries (2026-11-04).", "-- Previous snapshot retained solely for fallback ESTIMATES, not live CV data.")
     code=s.encode('utf-8');changed=True
    segments.append(struct.pack('<I',len(code))+code)
   raw=header+b''.join(segments)
   payload=lz4.block.compress(raw,store_size=False)
   comp=len(payload);uncomp=len(raw)
 new.extend(tag+struct.pack('<III',comp,uncomp,res)+payload)
 count+=1
 if tag==b'END\x00':break
if not changed:raise RuntimeError('Arcade price function was not found; original file remains unchanged')
DST.write_bytes(new)
# Strict structure read-back / bytes and decompress validation
p=32;checked=0;verified=False
b=DST.read_bytes()
while p+16<=len(b):
 tag=b[p:p+4];cl,ul,rs=struct.unpack_from('<III',b,p+4);data=b[p+16:p+16+(cl or ul)];p+=16+(cl or ul)
 if cl and len(lz4.block.decompress(data,uncompressed_size=ul))!=ul:raise RuntimeError('Bad compression')
 if tag==b'PROP':
  raw=lz4.block.decompress(data,uncompressed_size=ul) if cl else data
  L=struct.unpack_from('<I',raw,4)[0]
  if raw[8:8+L]==b'Source' and b'CV_RAP_ENDPOINT' in raw:verified=True
 checked+=1
 if tag==b'END\x00':break
assert verified and p==len(b),(verified,p,len(b))
print('PATCHED',DST, 'bytes',len(b),'chunks',checked, 'scripts changed',int(changed))
