// Phone host for the original Ankang ProductService. No desktop microphone,
// remote model, OCR, webhook or HealthKit is enabled by inherited environment.
const readline = require('node:readline');
const path = require('node:path');
const route = path.resolve(__dirname, '../ankang/route1-health-agent');
const {ProductService} = require(path.join(route, '.bridge-build/product/ProductService.js'));
const {ProductLocalStore} = require(path.join(route, 'scripts/product-local-store.cjs'));
const {normalizeMedicationProfile} = require(path.join(route, '.bridge-build/medication/medications.js'));
const store = new ProductLocalStore(process.argv[2]);
const product = new ProductService(store);
console.log = console.error;
let queue = Promise.resolve();
const input = readline.createInterface({input:process.stdin, crlfDelay:Infinity});
input.on('line', line => {
  queue = queue.then(async () => {
    try {
      const r = JSON.parse(line);
      if(r.operation !== 'product') throw Error('Unsupported mobile host operation');
      if(r.productOperation === 'mobile.restore') {
        const owner=r.sessionId,p=r.payload;
        if(!/^[a-f0-9]{32}$/.test(owner) || !p?.profile || !Array.isArray(p.events) || !Array.isArray(p.chat) || !Array.isArray(p.attachments)) throw Error('Invalid restore input');
        if(store.read('profile:'+owner)) throw Error('当前已有健康档案，不能覆盖恢复');
        const scope={ownerId:owner,dataMode:'personal'}, key='personal:'+owner;
        // Profile is the commit marker. Interrupted imports remain invisible and retryable.
        store.write(store.attachmentKey(scope),p.attachments.map(a=>({...a,...scope,visibility:'private'})));
        store.write('health:'+key,{revision:1,health:{events:p.events,familyEvents:[],chat:p.chat}});
        store.write('profile:'+owner,{version:1,...scope,profile:normalizeMedicationProfile(p.profile)});
        const result=await product.request('snapshot',owner,{},new Date(r.now));
        process.stdout.write(JSON.stringify({ok:true,result})+'\n');return;
      }
      const result = await product.request(r.productOperation, r.sessionId, r.payload || {}, new Date(r.now));
      process.stdout.write(JSON.stringify({ok:true,result})+'\n');
    } catch(e) {process.stdout.write(JSON.stringify({ok:false,error:e.message})+'\n');}
  });
});
