import httpx,hashlib
from bs4 import BeautifulSoup
from urllib.parse import urljoin
async def public_career_page(s):
 url=s.get('base_url');
 if not url:return []
 async with httpx.AsyncClient(timeout=20,follow_redirects=True,headers={'User-Agent':'JobHubAI/1.0'}) as c: r=await c.get(url); r.raise_for_status()
 soup=BeautifulSoup(r.text,'html.parser'); out=[]
 for card in soup.select('article,.job,.job-card,[data-job-id]')[:100]:
  h=card.select_one('h1,h2,h3,h4,.title,[data-title]'); a=card.select_one('a[href]')
  if not h:continue
  href=urljoin(url,a['href']) if a else url
  out.append({'title':h.get_text(' ',strip=True),'company':s.get('company','Company'),'location':s.get('location',''),'description':card.get_text(' ',strip=True)[:5000],'skills':[],'job_type':'Full-time','work_mode':'On-site','source':s['name'],'source_url':href,'external_id':hashlib.sha1(href.encode()).hexdigest()})
 return out
