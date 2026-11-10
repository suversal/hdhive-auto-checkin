// Optional rebuild: npm install --no-save esbuild@0.28.1, then node build.mjs.
// The shipped app.js and local React vendors require no installation or network.
import {readFileSync,writeFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {createRequire} from 'node:module';
import path from 'node:path';
const require=createRequire(import.meta.url);
const esbuild=process.env.SHIKE_ESBUILD_PATH?require(process.env.SHIKE_ESBUILD_PATH):require('esbuild');
const dir=path.dirname(fileURLToPath(import.meta.url));
const files=['icons.jsx','data.js','components.jsx','views.jsx','flows.jsx','app.jsx'];
const source=files.map(file=>readFileSync(path.join(dir,file),'utf8')).join('\n');
const built=esbuild.transformSync(source,{loader:'jsx',target:'es2020',jsx:'transform',minify:false,legalComments:'inline'});
writeFileSync(path.join(dir,'app.js'),built.code);
console.log('Built app.js from '+files.length+' source files.');
