"""Local evidence manifest/CSV/contact sheets; no application or user data reads."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image,ImageDraw

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    entries=[('care-http','HTTP照护'),('extended-http-r2','HTTP边界/过期'),('state-http','HTTP语义/家庭'),
             ('crash-http','HTTP崩溃'),('current-desktop-final','Qt当前界面'),('full-web-r2/browser','Edge完整界面')]
    rows=[];summary={}
    for folder,label in entries:
        data=json.loads((root/folder/'results.json').read_text(encoding='utf-8'))
        summary[label]={'counts':data['counts'],'completed':data.get('completed',True),'path':folder+'/results.json'}
        for c in data['cases']:
            rows.append({'suite':label,'id':c.get('id',''),'name':c.get('title',c.get('name')),'status':c['status'],
                         'expected':c.get('expected',''),'detail':str(c.get('evidence',c.get('detail','')))[:3000]})
    with (root/'cases.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    for folder,prefix in [('full-web-r2/browser','web'),('current-desktop-final','desktop')]:
        images=sorted((root/folder).glob('[0-9][0-9].png'))
        for start in range(0,len(images),12):
            board=Image.new('RGB',(1200,4*310),'#dddddd');draw=ImageDraw.Draw(board)
            for i,path in enumerate(images[start:start+12]):
                with Image.open(path) as source:
                    source.thumbnail((390,280));x=(i%3)*400;y=(i//3)*310
                    board.paste(source,(x,y+25));draw.text((x+5,y+5),path.stem,fill='black')
            board.save(root/f'contact-{prefix}-{start//12+1}.png')
    files=[]
    for file in sorted(root.rglob('*')):
        if file.is_file() and file.name!='manifest.json':
            files.append({'path':str(file.relative_to(root)),'bytes':file.stat().st_size,
                          'sha256':hashlib.sha256(file.read_bytes()).hexdigest()})
    result={'baseline':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),
            'suites':summary,'files':files,'note':'legacy harness attempts and rechecks retained; final suites listed separately'}
    (root/'manifest.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
