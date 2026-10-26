const fs = require('fs');
const path = require('path');

const version = process.argv[2];
if (!version) {
  console.error('Usage: node scripts/set-version.js <version> (e.g. 0.2.3)');
  process.exit(1);
}

const cleanVersion = version.replace(/^v/, '');
console.log(`Setting version to ${cleanVersion}...`);

// 1. package.json
const rootPkgPath = path.resolve(__dirname, '../package.json');
const rootPkg = JSON.parse(fs.readFileSync(rootPkgPath, 'utf8'));
rootPkg.version = cleanVersion;
fs.writeFileSync(rootPkgPath, JSON.stringify(rootPkg, null, 2) + '\n', 'utf8');
console.log('✓ Updated package.json');

// 2. frontend/package.json
const frontPkgPath = path.resolve(__dirname, '../frontend/package.json');
const frontPkg = JSON.parse(fs.readFileSync(frontPkgPath, 'utf8'));
frontPkg.version = cleanVersion;
fs.writeFileSync(frontPkgPath, JSON.stringify(frontPkg, null, 2) + '\n', 'utf8');
console.log('✓ Updated frontend/package.json');

console.log(`\nAll version references synchronized to ${cleanVersion}!`);
