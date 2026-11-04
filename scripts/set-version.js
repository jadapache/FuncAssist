const fs = require('fs');
const path = require('path');

const version = process.argv[2];
if (!version) {
  console.error('Usage: node scripts/set-version.js <version> (e.g. 0.2.3)');
  process.exit(1);
}

const cleanVersion = version.replace(/^v/, '');
console.log(`Setting version to ${cleanVersion}...`);

function updatePackageVersion(packagePath, lockPath) {
  const packageJson = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
  packageJson.version = cleanVersion;
  fs.writeFileSync(packagePath, JSON.stringify(packageJson, null, 2) + '\n', 'utf8');

  // npm lockfiles v2/v3 store the root package version in both places.
  if (fs.existsSync(lockPath)) {
    const lockJson = JSON.parse(fs.readFileSync(lockPath, 'utf8'));
    lockJson.version = cleanVersion;
    if (lockJson.packages && lockJson.packages['']) {
      lockJson.packages[''].version = cleanVersion;
    }
    fs.writeFileSync(lockPath, JSON.stringify(lockJson, null, 2) + '\n', 'utf8');
  }
}

// 1. package.json
const rootPkgPath = path.resolve(__dirname, '../package.json');
const rootLockPath = path.resolve(__dirname, '../package-lock.json');
const rootPkg = JSON.parse(fs.readFileSync(rootPkgPath, 'utf8'));
rootPkg.version = cleanVersion;
fs.writeFileSync(rootPkgPath, JSON.stringify(rootPkg, null, 2) + '\n', 'utf8');
updatePackageVersion(rootPkgPath, rootLockPath);
console.log('✓ Updated package.json');

// 2. frontend/package.json
const frontPkgPath = path.resolve(__dirname, '../frontend/package.json');
const frontLockPath = path.resolve(__dirname, '../frontend/package-lock.json');
const frontPkg = JSON.parse(fs.readFileSync(frontPkgPath, 'utf8'));
frontPkg.version = cleanVersion;
fs.writeFileSync(frontPkgPath, JSON.stringify(frontPkg, null, 2) + '\n', 'utf8');
updatePackageVersion(frontPkgPath, frontLockPath);
console.log('✓ Updated frontend/package.json');

console.log(`\nAll version references synchronized to ${cleanVersion}!`);
