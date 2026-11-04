const fs = require('fs');
const path = require('path');

function parseVersionArgument() {
  const version = process.argv[2];
  if (!version) {
    console.error('Usage: node scripts/set-version.js <version> (e.g. 0.3.3)');
    process.exit(1);
  }
  return version.replace(/^v/, '');
}

function updatePackageVersion(packagePath, lockPath, cleanVersion) {
  if (!fs.existsSync(packagePath)) {
    return;
  }
  const packageJson = JSON.parse(fs.readFileSync(packagePath, 'utf8'));
  packageJson.version = cleanVersion;
  fs.writeFileSync(packagePath, JSON.stringify(packageJson, null, 2) + '\n', 'utf8');

  if (!fs.existsSync(lockPath)) {
    return;
  }
  const lockJson = JSON.parse(fs.readFileSync(lockPath, 'utf8'));
  lockJson.version = cleanVersion;
  if (lockJson.packages && lockJson.packages['']) {
    lockJson.packages[''].version = cleanVersion;
  }
  fs.writeFileSync(lockPath, JSON.stringify(lockJson, null, 2) + '\n', 'utf8');
}

function updateFastApiVersion(mainPyPath, cleanVersion) {
  if (!fs.existsSync(mainPyPath)) {
    return;
  }
  const content = fs.readFileSync(mainPyPath, 'utf8');
  const updated = content.replace(
    /(version\s*=\s*["'])[^"']+(["'])/,
    `$1${cleanVersion}$2`
  );
  fs.writeFileSync(mainPyPath, updated, 'utf8');
}

function updateEnvVersion(envPath, cleanVersion) {
  if (!fs.existsSync(envPath)) {
    return;
  }
  const content = fs.readFileSync(envPath, 'utf8');
  const eol = content.includes('\r\n') ? '\r\n' : '\n';
  const appVersionRegex = /^APP_VERSION=.*$/m;
  const updated = appVersionRegex.test(content)
    ? content.replace(appVersionRegex, `APP_VERSION=${cleanVersion}`)
    : `${content.trimEnd()}${eol}APP_VERSION=${cleanVersion}${eol}`;
  fs.writeFileSync(envPath, updated, 'utf8');
}

function synchronizeVersions() {
  const cleanVersion = parseVersionArgument();
  console.log(`Setting version to ${cleanVersion}...`);

  const rootDir = path.resolve(__dirname, '..');
  updatePackageVersion(
    path.join(rootDir, 'package.json'),
    path.join(rootDir, 'package-lock.json'),
    cleanVersion
  );
  console.log('[OK] Updated package.json');

  updatePackageVersion(
    path.join(rootDir, 'frontend', 'package.json'),
    path.join(rootDir, 'frontend', 'package-lock.json'),
    cleanVersion
  );
  console.log('[OK] Updated frontend/package.json');

  updateFastApiVersion(
    path.join(rootDir, 'backend', 'app', 'main.py'),
    cleanVersion
  );
  console.log(`\nAll version references synchronized to ${cleanVersion}!`);
}

synchronizeVersions();
