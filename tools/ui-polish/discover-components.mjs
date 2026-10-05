// Read-only registry discovery. Never installs a component or executes fetched code.
import fs from 'node:fs/promises';
import path from 'node:path';
const names = ['WarmTooltip','RubberSegment','GlideSelect','PromptBar','BranchedMenu'];
const query = process.argv[2] || 'all';
const aliases = {tooltip:'WarmTooltip',segment:'RubberSegment',select:'GlideSelect',input:'PromptBar',prompt:'PromptBar',menu:'BranchedMenu',navigation:'BranchedMenu'};
let chosen = query === 'all' ? names : names.filter(n => n.toLowerCase().includes(query.toLowerCase()) || n === aliases[query.toLowerCase()]);
if (!chosen.length) {
  const response = await fetch('https://reactbits.dev/r/registry.json',{signal:AbortSignal.timeout(30000)});
  if (!response.ok) throw new Error(`Registry index: ${response.status}`);
  const index = await response.json();
  if (!Array.isArray(index.items)) throw new Error('Invalid registry index');
  const tokens=query.toLowerCase().split(/\s+/).filter(Boolean);
  chosen=index.items.filter(x=>x.name.endsWith('-TS-CSS') && tokens.every(t=>`${x.title} ${x.description} ${x.name}`.toLowerCase().includes(t))).slice(0,8).map(x=>x.name.replace(/-TS-CSS$/,''));
  if (!chosen.length) throw new Error(`No registry match for ${query}; inspect alternative libraries or refine the query before inventing.`);
}
const output = process.argv[3] || 'qa-output/ui-env/discovery';
await fs.mkdir(output,{recursive:true});
const results = [];
for (const name of chosen) {
  const url = `https://reactbits.dev/r/${name}-TS-CSS.json`;
  const response = await fetch(url,{signal:AbortSignal.timeout(30000)});
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  const item = await response.json();
  if (item.name !== `${name}-TS-CSS` || !Array.isArray(item.files)) throw new Error(`Invalid registry item: ${name}`);
  const source = item.files.filter(f => /tsx$/.test(f.path)).map(f=>f.content).join('\n');
  const props = [...source.matchAll(/(?:export\s+)?(?:interface|type)\s+(\w*Props)\s*(?:=\s*)?\{([\s\S]*?)\n\}/g)].map(m=>({name:m[1],definition:m[2].trim()}));
  const slug = name.replace(/([a-z])([A-Z])/g,'$1-$2').toLowerCase();
  const record = {name,description:item.description,dependencies:item.dependencies || [],registryDependencies:item.registryDependencies || [],props,
    sourceMethod:url,installation:`npx shadcn add https://reactbits.dev/r/${name}-TS-CSS.json`,preview:`https://reactbits.dev/c/micro/${slug}`,
    sourceFiles:item.files.map(f=>f.path),fetchedAt:new Date().toISOString(),license:'MIT + Commons Clause; check upstream LICENSE.md before adaptation'};
  await fs.writeFile(path.join(output,`${name}.json`),JSON.stringify(item,null,2));
  results.push(record);
}
await fs.writeFile(path.join(output,'catalog.json'),JSON.stringify(results,null,2));
console.log(JSON.stringify(results,null,2));
