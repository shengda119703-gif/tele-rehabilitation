// Phone host for the original Ankang ProductService. No desktop microphone,
// remote model, OCR, webhook or HealthKit is enabled by inherited environment.
const readline = require('node:readline');
const path = require('node:path');
const route = path.resolve(__dirname, '../ankang/route1-health-agent');
const {ProductService} = require(path.join(route, '.bridge-build/product/ProductService.js'));
const {ProductLocalStore} = require(path.join(route, 'scripts/product-local-store.cjs'));
const product = new ProductService(new ProductLocalStore(process.argv[2]));
console.log = console.error;
let queue = Promise.resolve();
const input = readline.createInterface({input:process.stdin, crlfDelay:Infinity});
input.on('line', line => {
  queue = queue.then(async () => {
    try {
      const r = JSON.parse(line);
      if(r.operation !== 'product') throw Error('Unsupported mobile host operation');
      const result = await product.request(r.productOperation, r.sessionId, r.payload || {}, new Date(r.now));
      process.stdout.write(JSON.stringify({ok:true,result})+'\n');
    } catch(e) {process.stdout.write(JSON.stringify({ok:false,error:e.message})+'\n');}
  });
});
