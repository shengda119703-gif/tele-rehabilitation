// Bundle the actual upstream domain service, not a second set of health rules.
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../../ankang/route1-health-agent');
const ts=require(path.join(root,'node_modules/typescript'));
const modules=new Map();
function collect(file){
 const id=path.relative(root,file).replaceAll('\\','/').replace(/\.ts$/,'');if(modules.has(id))return id;
 let code=ts.transpileModule(fs.readFileSync(file,'utf8'),{fileName:file,compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS}}).outputText;
 modules.set(id,'');
 code=code.replace(/require\("([^"\n]+)"\)/g,(match,dependency)=>{
  if(!dependency.startsWith('.'))throw Error('Unexpected non-browser dependency: '+dependency+' in '+file);
  const child=path.resolve(path.dirname(file),dependency)+'.ts';return 'require('+JSON.stringify(collect(child))+')';
 });modules.set(id,code);return id;
}
const entry=collect(path.join(root,'src/product/ProductService.ts'));
const output='(function(){"use strict";const factories={'+[...modules].map(([id,code])=>JSON.stringify(id)+':function(module,exports,require){\n'+code+'\n}').join(',')+'};const cache={};function require(id){if(cache[id])return cache[id].exports;const m=cache[id]={exports:{}};if(!factories[id])throw Error("Missing domain module "+id);factories[id](m,m.exports,require);return m.exports;}globalThis.AnkangDomain=require('+JSON.stringify(entry)+');})();';
fs.mkdirSync(path.resolve(__dirname,'../build/assets/local'),{recursive:true});
fs.writeFileSync(path.resolve(__dirname,'../build/assets/local/product.js'),output);
console.log('Bundled '+modules.size+' original domain modules');
