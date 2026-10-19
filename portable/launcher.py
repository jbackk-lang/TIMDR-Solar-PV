"""Local portable launcher. It stops only its own server instance."""
from pathlib import Path
import argparse,json,os,secrets,subprocess,sys,time,urllib.request,urllib.error,webbrowser,threading,socket
ROOT=Path(__file__).resolve().parent
STATE=ROOT/'runtime';INSTANCE=STATE/'instance.json'

def read_instance():
 try:return json.loads(INSTANCE.read_text(encoding='utf-8'))
 except (OSError,ValueError):return None

def request(info,path='/api/portable-identity',payload=None):
 url='http://127.0.0.1:'+str(info['port'])
 headers={'Content-Type':'application/json','Origin':url}
 if payload is not None:headers['X-Portable-Token']=info['token']
 req=urllib.request.Request(url+path,data=json.dumps(payload).encode() if payload is not None else None,headers=headers)
 with urllib.request.urlopen(req,timeout=2) as response:return json.load(response)

def alive(info):
 if not info:return False
 try:return request(info).get('instance')==info['instance']
 except (OSError,ValueError,KeyError):return False

def serve(port):
 from api import app
 from flask import jsonify,request as incoming
 from werkzeug.serving import make_server
 token=secrets.token_urlsafe(32);identity=secrets.token_hex(16)
 @app.get('/api/portable-identity')
 def identity_route():return jsonify(application='TIMDR-Solar-PV-portable',instance=identity)
 @app.post('/api/portable-stop')
 def stop_route():
  expected='http://127.0.0.1:'+str(server.server_port)
  if incoming.headers.get('Origin')!=expected or not secrets.compare_digest(incoming.headers.get('X-Portable-Token',''),token):return jsonify(error='Invalid server identity'),403
  threading.Thread(target=server.shutdown,daemon=True).start();return jsonify(status='stopping')
 server=make_server('127.0.0.1',port,app,threaded=True)
 info={'application':'TIMDR-Solar-PV-portable','instance':identity,'token':token,'port':server.server_port,'pid':os.getpid()}
 STATE.mkdir(exist_ok=True);temp=STATE/'instance.tmp';temp.write_text(json.dumps(info),encoding='utf-8');temp.replace(INSTANCE)
 try:server.serve_forever()
 finally:
  server.server_close()
  if (read_instance() or {}).get('instance')==identity:INSTANCE.unlink(missing_ok=True)

def start(port,no_browser):
 info=read_instance()
 if not alive(info):
  with socket.socket() as probe:
   try:probe.bind(('127.0.0.1',port))
   except OSError:probe.bind(('127.0.0.1',0))
   port=probe.getsockname()[1]
  print('Uruchamiam TIMDR Solar PV. Pierwszy start moze potrwac chwile...',flush=True)
  STATE.mkdir(exist_ok=True)
  with (STATE/'server.log').open('ab') as log:
   child=subprocess.Popen([sys.executable,'-B',str(ROOT/'launcher.py'),'serve','--port',str(port)],cwd=ROOT,stdout=log,stderr=log,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
  for _ in range(900):
   info=read_instance()
   if alive(info):break
   if child.poll() is not None:raise RuntimeError('Serwer nie wystartowal. Zobacz runtime/server.log.')
   time.sleep(.1)
  else:raise RuntimeError('Brak odpowiedzi serwera. Zobacz runtime/server.log.')
 url='http://127.0.0.1:'+str(info['port']);print('TIMDR Solar PV: '+url)
 if not no_browser:webbrowser.open(url)
 return info

def main():
 p=argparse.ArgumentParser();p.add_argument('action',choices=['start','stop','status','serve']);p.add_argument('--port',type=int,default=5001);p.add_argument('--no-browser',action='store_true');args=p.parse_args()
 if args.action=='serve':serve(args.port)
 elif args.action=='start':start(args.port,args.no_browser)
 elif args.action=='stop':
  info=read_instance()
  if alive(info):request(info,'/api/portable-stop',{});print('Zatrzymano serwer tej paczki.')
  else:print('Serwer tej paczki nie jest uruchomiony.')
 else:print(json.dumps({'running':alive(read_instance()),'port':(read_instance() or {}).get('port')}))
if __name__=='__main__':
 try:main()
 except Exception as exc:print('BLAD: '+str(exc),file=sys.stderr);sys.exit(1)
