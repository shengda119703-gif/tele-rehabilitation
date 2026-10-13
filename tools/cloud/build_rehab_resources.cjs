'use strict';
// Export the same built, curated sources used by the local question-and-plan UI.
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'../..');
const {catalogue}=require(path.join(root,'ankang/route1-health-agent/.bridge-build/rehab/catalogue.js'));
const {starterRules}=require(path.join(root,'ankang/route1-health-agent/.bridge-build/rehab/planRules.js'));
if(catalogue.length!==185||starterRules.length!==5)throw Error('Rebuild and review shared resources before exporting');
fs.writeFileSync(path.join(root,'cloud_service/rehab_resources.json'),JSON.stringify({schema:'ankang-rehab-resources-1',source:'docs/rehab-library/SOURCE_v1.0.md',cards:catalogue,rules:starterRules},null,2)+'\n');
