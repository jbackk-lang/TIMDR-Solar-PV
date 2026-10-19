"""Build Windows x64 portable from the current source; no runtime installs."""
from pathlib import Path
import argparse,hashlib,json,shutil,subprocess,sys,urllib.request,zipfile,datetime,importlib.metadata
PYTHON_URL='https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip'
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--runtime-zip');parser.add_argument('--site-packages',help='Reuse a trusted Windows CPython 3.12 x64 environment');args=parser.parse_args()
 source=Path(__file__).resolve().parents[1];assets=Path(__file__).resolve().parent;out=Path(args.output).resolve()
 if out.exists():raise SystemExit('Output must be a new directory.')
 out.mkdir(parents=True);runtime=out/'python';runtime.mkdir();app=out/'app';app.mkdir()
 archive=Path(args.runtime_zip).resolve() if args.runtime_zip else out.parent/'python-3.12.10-embed-amd64.zip'
 if not archive.exists():urllib.request.urlretrieve(PYTHON_URL,archive)
 with zipfile.ZipFile(archive) as z:z.extractall(runtime)
 (runtime/'python312._pth').write_text('python312.zip\n.\nLib/site-packages\n../app\n',encoding='ascii')
 target=runtime/'Lib/site-packages';target.mkdir(parents=True)
 if args.site_packages:
  packages=Path(args.site_packages)
  for item in packages.iterdir():
   if item.name=='__pycache__' or item.name=='pip' or item.name.startswith('pip-'):continue
   if item.is_dir():shutil.copytree(item,target/item.name,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
   else:shutil.copy2(item,target/item.name)
 else:subprocess.run([sys.executable,'-m','pip','install','--only-binary=:all:','--target',str(target),'-r',str(assets/'requirements-lock.txt')],check=True)
 # The application contains source and tests, never Git history or local venvs.
 for item in source.iterdir():
  if item.is_file() and (item.suffix=='.py' or item.name in ('LICENSE','README.md','requirements.txt')):shutil.copy2(item,app/item.name)
 shutil.copytree(source/'static',app/'static')
 for name in ['launcher.py','START.bat','STOP.bat','TESTY.bat','CZYTAJ.txt','requirements-lock.txt']:shutil.copy2(assets/name,out/name)
 (out/'runtime').mkdir()
 try:commit=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
 except (OSError,subprocess.CalledProcessError):commit='source-export'
 versions=sorted([{'name':d.metadata['Name'],'version':d.version} for d in importlib.metadata.distributions(path=[str(target)])],key=lambda x:x['name'].lower())
 expected=dict(line.strip().split('==',1) for line in (assets/'requirements-lock.txt').read_text().splitlines() if line.strip())
 observed={d['name'].lower().replace('_','-'):d['version'] for d in versions}
 for name,version in expected.items():
  if observed.get(name.lower().replace('_','-'))!=version:raise RuntimeError('Dependency version mismatch: '+name)
 manifest={'application':'TIMDR-Solar-PV-portable','platform':'Windows x64','python':'3.12.10','runtime_source':PYTHON_URL,'runtime_sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'source_commit':commit,'built_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'packages':versions}
 (out/'BUILD-MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
 (out/'LICENSE').write_bytes((source/'LICENSE').read_bytes())
 print(json.dumps({'output':str(out),'files':sum(1 for p in out.rglob('*') if p.is_file()),'bytes':sum(p.stat().st_size for p in out.rglob('*') if p.is_file())}))
if __name__=='__main__':main()
