// Copies the pinned Alpine.js build (package.json devDependency alpinejs 3.17.5) into static/vendor/.
// Usage: npm ci && npm run build:vendor      (Node 18+; only needed to update the vendored file)
const fs = require("fs");
const path = require("path");
const root = path.resolve(__dirname, "..");
const src = path.join(root, "node_modules", "alpinejs", "dist", "cdn.min.js");
const pkg = require(path.join(root, "node_modules", "alpinejs", "package.json"));
fs.copyFileSync(src, path.join(root, "static", "vendor", "alpine.min.js"));
console.log(`static/vendor/alpine.min.js <- alpinejs ${pkg.version} dist/cdn.min.js`);
