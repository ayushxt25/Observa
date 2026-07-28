import { gzipSync } from "node:zlib";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const chunksDir = join(process.cwd(), ".next", "static", "chunks");

function collectJavaScriptFiles(directory) {
  const entries = readdirSync(directory, { withFileTypes: true });
  const files = [];

  for (const entry of entries) {
    const fullPath = join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectJavaScriptFiles(fullPath));
    } else if (entry.isFile() && entry.name.endsWith(".js") && !entry.name.endsWith(".js.map")) {
      files.push(fullPath);
    }
  }

  return files;
}

const files = collectJavaScriptFiles(chunksDir);
let rawBytes = 0;
let gzipBytes = 0;

for (const file of files) {
  const raw = readFileSync(file);
  rawBytes += statSync(file).size;
  gzipBytes += gzipSync(raw).byteLength;
}

console.log("PulseGrid browser JavaScript asset size");
console.log(`Directory: ${relative(process.cwd(), chunksDir)}`);
console.log("Method: recursively sum .js files; source maps are excluded; gzip uses node:zlib gzipSync per asset.");
console.log("Note: aggregate build-asset measurement; may include shared chunks not all loaded on the dashboard route.");
console.log(`JavaScript files counted: ${files.length}`);
console.log(`Raw total bytes: ${rawBytes}`);
console.log(`Gzip total bytes: ${gzipBytes}`);
