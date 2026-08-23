import asyncio, os, json, urllib.request, urllib.error, http.client
os.environ.setdefault('APP_ENV', 'local')
from app.database import async_session
from app.models.resume import Resume
from app.models.user import User
from sqlalchemy import select
from jose import jwt
from app.config import get_settings

S = get_settings()

async def pick():
    async with async_session() as s:
        rs = (await s.execute(select(Resume))).scalars().all()
        for r in rs:
            u = (await s.execute(select(User).where(User.id == r.user_id))).scalar_one_or_none()
            st = (r.parsed_data or {}).get('structured') or {}
            we = st.get('work_experience') or []
            if u and len(we) > 0:
                return r.id, u.email
    return None, None

RID, email = asyncio.run(pick())
print('RID', RID, 'owner', email)
assert RID, 'no candidate found'

async def tok_for(email):
    async with async_session() as s:
        u = (await s.execute(select(User).where(User.email == email))).scalar_one()
        return jwt.encode({'sub': str(u.id), 'type': 'access'}, S.SECRET_KEY, algorithm='HS256')

tok = asyncio.run(tok_for(email))

def get_json(path):
    req = urllib.request.Request('http://127.0.0.1:8000' + path)
    req.add_header('Authorization', 'Bearer ' + tok)
    try:
        resp = urllib.request.urlopen(req, timeout=60)
        return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()

def describe(st):
    we = st.get('work_experience') or []
    lines = [f'work_experience count={len(we)}']
    for w in we[:2]:
        d = w.get('description') or ''
        lines.append(f"  - {w.get('company')} {w.get('title')} | desc_len={len(d)} | {d[:120]!r}")
    return '\n'.join(lines)

_, body = get_json(f'/resumes/{RID}')
before = json.loads(body).get('parsed_data', {}).get('structured', {})
print('BEFORE:\n' + describe(before))

JD = '高级后端工程师，要求 5 年以上经验，精通 Go/Python、微服务、Kubernetes、分布式系统，有大流量高并发经验者优先。'
conn = http.client.HTTPConnection('127.0.0.1', 8000, timeout=180)
conn.request('POST', f'/resumes/{RID}/polish', body=json.dumps({'jd_text': JD}).encode(),
             headers={'Authorization': 'Bearer ' + tok, 'Content-Type': 'application/json'})
resp = conn.getresponse()
print('polish HTTP', resp.status)
polished = []
for raw in resp.read().decode().split('\n\n'):
    if raw.startswith('data: '):
        d = raw[6:].strip()
        if d in ('[DONE]', ''):
            continue
        try:
            o = json.loads(d)
            if 'content' in o:
                polished.append(o['content'])
            if 'error' in o:
                print('STREAM ERROR:', o['error'])
        except Exception:
            pass
conn.close()
print('polished_text len:', len(''.join(polished)))

_, body2 = get_json(f'/resumes/{RID}')
after = json.loads(body2).get('parsed_data', {}).get('structured', {})
print('AFTER:\n' + describe(after))
print('STRUCTURED CHANGED?', json.dumps(before, sort_keys=True) != json.dumps(after, sort_keys=True))
