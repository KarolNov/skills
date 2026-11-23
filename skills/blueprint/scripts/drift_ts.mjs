#!/usr/bin/env node
// Import closures of TS/JS capabilities, resolved by symbol with the repo's own typescript.
// drift.py runs this; it is not meant to be run by hand. Node's standard library only.
//
// stdin:  {"root": "/abs/repo", "maxDepth": 6, "sideEffects": {"<package>": false | true | [globs]},
//          "capabilities": {"<name>": ["repo/relative/anchored.ts", ...]}}
// stdout: {"typescript": "<version>", "closures": {"<name>": {
//            "nodes": [{"file", "symbol" (null: the whole file), "distance", "via", "hash"?}],
//            "external": ["<package>", ...]}}}
// exit 3: typescript can't be loaded from the repo (drift.py then follows imports by file).
//
// A node is what a capability's anchored files depend on, like an editor's "go to
// definition": a top-level declaration (by symbol) or a whole file. Its distance counts
// import edges from the anchored files; barrels and re-exports are transparent, so a symbol
// is reported where it is declared. `via` lists the workspace packages the path enters. A
// named import from a package without side effects depends on the imported declarations and
// on what they reference; a bare import, or any import from a package with side effects,
// depends on the whole file and everything it imports. Packages come from the nearest
// package.json; its `sideEffects` field decides (absent means it has side effects), unless
// drift.scoring.packages overrides it. node_modules are leaves: only their names are kept.

import { createRequire } from "node:module";
import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

const input = JSON.parse(fs.readFileSync(0, "utf8"));
const root = fs.realpathSync(input.root);
const maxDepth = input.maxDepth ?? 6;
const overrides = input.sideEffects ?? {};

let ts;
try {
  ts = createRequire(path.join(root, "package.json"))("typescript");
} catch {
  process.stderr.write("typescript not installed\n");
  process.exit(3);
}

const rel = (file) => path.relative(root, file).split(path.sep).join("/");
const sha = (text) => crypto.createHash("sha256").update(text).digest("hex").slice(0, 12);

// Packages: the nearest package.json at or above a file, inside the repo.

const pkgCache = new Map();
function packageOf(dir) {
  if (pkgCache.has(dir)) return pkgCache.get(dir);
  let pkg = null;
  const manifest = path.join(dir, "package.json");
  if (fs.existsSync(manifest)) {
    let json = {};
    try { json = JSON.parse(fs.readFileSync(manifest, "utf8")); } catch { /* unreadable: no name */ }
    const name = typeof json.name === "string" ? json.name : null;
    const effects = name && name in overrides ? overrides[name]
      : "sideEffects" in json ? json.sideEffects : true;
    pkg = { dir, name, effects };
  } else if (dir !== root && dir.startsWith(root + path.sep)) {
    pkg = packageOf(path.dirname(dir));
  }
  pkgCache.set(dir, pkg);
  return pkg;
}

function globRe(glob) {
  let out = "";
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (glob.startsWith("**/", i)) { out += "(?:.*/)?"; i += 2; }
    else if (glob.startsWith("**", i)) { out += ".*"; i += 1; }
    else if (c === "*") out += "[^/]*";
    else if (c === "?") out += "[^/]";
    else out += c.replace(/[.+^${}()|[\]\\]/g, "\\$&");
  }
  return new RegExp(`^${out}$`);
}

// Whether importing this file pulls in the whole of it: bundlers' sideEffects rules.
function sideEffects(file) {
  const pkg = packageOf(path.dirname(file));
  if (!pkg) return true;
  if (typeof pkg.effects === "boolean") return pkg.effects;
  if (!Array.isArray(pkg.effects)) return true;
  const inPkg = path.relative(pkg.dir, file).split(path.sep).join("/");
  return pkg.effects.some((g) => {
    const glob = g.replace(/^\.\//, "");
    // A pattern without a slash matches the file name anywhere, as bundlers read it.
    return globRe(glob).test(glob.includes("/") ? inPkg : path.posix.basename(inPkg));
  });
}

function externalName(file) {
  const parts = file.split(path.sep);
  const i = parts.lastIndexOf("node_modules");
  if (i < 0 || i + 1 >= parts.length) return null;
  return parts[i + 1].startsWith("@") ? `${parts[i + 1]}/${parts[i + 2]}` : parts[i + 1];
}

// The program: the repo's tsconfig when it has one, made to read JS and resolve like a bundler.

function compilerOptions() {
  const config = ts.findConfigFile(root, ts.sys.fileExists, "tsconfig.json");
  let options = {};
  if (config && path.dirname(fs.realpathSync(config)) === root) {
    const read = ts.readConfigFile(config, ts.sys.readFile);
    if (!read.error) options = ts.parseJsonConfigFileContent(read.config, ts.sys, root).options;
  }
  options = { ...options, allowJs: true, noEmit: true, skipLibCheck: true };
  if (options.moduleResolution === undefined) {
    const bundler = ts.ModuleResolutionKind.Bundler;
    options.module = bundler ? ts.ModuleKind.ESNext : ts.ModuleKind.CommonJS;
    options.moduleResolution = bundler ?? ts.ModuleResolutionKind.NodeJs;
  }
  return options;
}

const capabilities = input.capabilities ?? {};
const entryFiles = [...new Set(Object.values(capabilities).flat())].sort()
  .map((f) => path.join(root, f)).filter((f) => fs.existsSync(f));
const options = compilerOptions();
const program = ts.createProgram(entryFiles, options);
const checker = program.getTypeChecker();

// Where a declaration lives: a repo file, an external package, or nowhere we follow.
function placeOf(sf) {
  if (program.isSourceFileDefaultLibrary(sf)) return { kind: "skip" };
  let file = sf.fileName;
  try { file = fs.realpathSync(file); } catch { /* virtual file */ }
  // Workspace packages resolve through node_modules links too: the real path tells them apart.
  const ext = externalName(file);
  if (ext) return { kind: "external", name: ext };
  if (!file.startsWith(root + path.sep)) return { kind: "skip" };
  return { kind: "repo", file, rel: rel(file) };
}

function topStatement(node) {
  while (node.parent && !ts.isSourceFile(node.parent) && !ts.isModuleBlock(node.parent)) {
    node = node.parent;
  }
  // A declaration inside `declare module`/namespace counts as the outermost statement.
  while (node.parent && ts.isModuleBlock(node.parent)) node = node.parent.parent;
  return node.parent ? node : null;
}

function statementName(stmt) {
  if (ts.isVariableStatement(stmt)) {
    return stmt.declarationList.declarations.map((d) => d.name.getText()).join(",");
  }
  if (ts.isExportAssignment(stmt)) return "default";
  if (stmt.name) return stmt.name.getText();
  const mods = ts.canHaveModifiers?.(stmt) ? ts.getModifiers(stmt) ?? [] : stmt.modifiers ?? [];
  if (mods.some((m) => m.kind === ts.SyntaxKind.DefaultKeyword)) return "default";
  const { line } = stmt.getSourceFile().getLineAndCharacterOfPosition(stmt.getStart());
  return `line ${line + 1}`;
}

function resolveAlias(sym) {
  if (sym && sym.flags & ts.SymbolFlags.Alias) {
    try { return checker.getAliasedSymbol(sym); } catch { return sym; }
  }
  return sym;
}

function moduleFile(specifier) {
  if (!specifier) return null;
  const mod = checker.getSymbolAtLocation(specifier);
  const decl = mod?.valueDeclaration ?? mod?.declarations?.[0];
  if (decl && ts.isSourceFile(decl)) return decl;
  // A script (no imports or exports) has no module symbol: resolve the specifier instead.
  if (!ts.isStringLiteralLike(specifier)) return null;
  const found = ts.resolveModuleName(specifier.text, specifier.getSourceFile().fileName,
                                     options, ts.sys).resolvedModule;
  return (found && program.getSourceFile(found.resolvedFileName)) ?? null;
}

// Edges. Each is {kind: "file" | "symbol" | "external", ...} plus `same` when it stays in
// the file (no import edge crossed). Computed once per node, shared by every capability.

function wholeFile(sf) {
  const place = placeOf(sf);
  if (place.kind === "external") return [{ kind: "external", name: place.name }];
  if (place.kind !== "repo") return [];
  return [{ kind: "file", key: `F:${place.rel}`, file: place.file, rel: place.rel, sf }];
}

function symbolEdges(sym, fromFile) {
  const out = [];
  const byStmt = new Map();
  for (const decl of sym?.declarations ?? []) {
    const sf = decl.getSourceFile();
    const place = placeOf(sf);
    if (place.kind === "external") { out.push({ kind: "external", name: place.name }); continue; }
    if (place.kind !== "repo") continue;
    if (ts.isSourceFile(decl)) continue; // a namespace: its members are reached by name
    if (place.file !== fromFile && sideEffects(place.file)) { out.push(...wholeFile(sf)); continue; }
    const stmt = topStatement(decl);
    if (!stmt) continue;
    const name = statementName(stmt);
    const key = `S:${place.rel}#${name}`;
    if (!byStmt.has(key)) {
      byStmt.set(key, { kind: "symbol", key, file: place.file, rel: place.rel, name, stmts: [] });
    }
    const edge = byStmt.get(key);
    if (!edge.stmts.includes(stmt)) edge.stmts.push(stmt);
  }
  return [...out, ...byStmt.values()];
}

// What one import or re-export declaration in `sf` depends on.
function importEdges(stmt, sf) {
  const target = moduleFile(stmt.moduleSpecifier);
  if (!target) {
    const spec = stmt.moduleSpecifier && ts.isStringLiteral(stmt.moduleSpecifier)
      ? stmt.moduleSpecifier.text : null;
    if (spec && !spec.startsWith(".") && !spec.startsWith("/")) {
      const name = spec.startsWith("@") ? spec.split("/").slice(0, 2).join("/") : spec.split("/")[0];
      return [{ kind: "external", name }];
    }
    return [];
  }
  const place = placeOf(target);
  if (place.kind !== "repo") return wholeFile(target);
  const clause = ts.isImportDeclaration(stmt) ? stmt.importClause : stmt.exportClause;
  const bare = ts.isImportDeclaration(stmt) && !clause;
  if (bare || sideEffects(place.file)) return wholeFile(target);
  const syms = [];
  if (ts.isImportDeclaration(stmt)) {
    if (clause.name) syms.push(checker.getSymbolAtLocation(clause.name));
    const bindings = clause.namedBindings;
    if (bindings && ts.isNamespaceImport(bindings)) {
      syms.push(...checker.getExportsOfModule(checker.getSymbolAtLocation(stmt.moduleSpecifier)));
    } else if (bindings) {
      for (const el of bindings.elements) syms.push(checker.getSymbolAtLocation(el.name));
    }
  } else if (!clause || ts.isNamespaceExport(clause)) {
    syms.push(...checker.getExportsOfModule(checker.getSymbolAtLocation(stmt.moduleSpecifier)));
  } else {
    for (const el of clause.elements) {
      syms.push(checker.getExportSpecifierLocalTargetSymbol(el) ?? checker.getSymbolAtLocation(el.name));
    }
  }
  return syms.filter(Boolean).flatMap((s) => symbolEdges(resolveAlias(s), sf.fileName));
}

// Imports, re-exports, `import x = require()`, dynamic import() and require() in a whole file.
function fileEdges(sf) {
  const out = [];
  for (const stmt of sf.statements) {
    if ((ts.isImportDeclaration(stmt) || ts.isExportDeclaration(stmt)) && stmt.moduleSpecifier) {
      out.push(...importEdges(stmt, sf));
    } else if (ts.isImportEqualsDeclaration(stmt) && ts.isExternalModuleReference(stmt.moduleReference)) {
      const target = moduleFile(stmt.moduleReference.expression);
      if (target) out.push(...wholeFile(target));
    }
  }
  const visit = (node) => {
    if (ts.isCallExpression(node) && node.arguments.length === 1 && ts.isStringLiteralLike(node.arguments[0])
        && (node.expression.kind === ts.SyntaxKind.ImportKeyword
            || (ts.isIdentifier(node.expression) && node.expression.text === "require"))) {
      const target = moduleFile(node.arguments[0]);
      if (target) out.push(...wholeFile(target));
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return out;
}

// What a top-level declaration references: the declarations its identifiers resolve to.
function declarationEdges(edge) {
  const out = [];
  const own = new Set(edge.stmts);
  const visit = (node) => {
    if (ts.isIdentifier(node) || ts.isPrivateIdentifier?.(node)) {
      const sym = checker.getSymbolAtLocation(node);
      if (sym) {
        const decl = sym.declarations?.[0];
        // An imported name: the import decides (a package with side effects means the whole file).
        const imp = decl && (ts.isImportSpecifier(decl) || ts.isImportClause(decl) || ts.isNamespaceImport(decl))
          ? decl.parent && ts.findAncestor(decl, ts.isImportDeclaration) : null;
        const target = imp && moduleFile(imp.moduleSpecifier);
        if (target && placeOf(target).kind === "repo" && sideEffects(target.fileName)) {
          out.push(...wholeFile(target));
        } else {
          out.push(...symbolEdges(resolveAlias(sym), edge.file)
            .filter((e) => e.kind !== "symbol" || !e.stmts.some((s) => own.has(s))));
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  for (const stmt of edge.stmts) visit(stmt);
  return out;
}

const edgeCache = new Map();
function edgesOf(node) {
  if (!edgeCache.has(node.key)) {
    const raw = node.kind === "file" ? fileEdges(node.sf) : declarationEdges(node);
    edgeCache.set(node.key, raw.map((e) => ({ ...e, same: e.kind !== "external" && e.file === node.file })));
  }
  return edgeCache.get(node.key);
}

// One capability's closure: a 0-1 breadth-first walk (same-file references cost no edge), so
// each node keeps its shortest distance, found in a fixed order.

function closure(entries) {
  const entrySet = new Set(entries.map((f) => path.join(root, f)));
  const best = new Map();
  const external = new Set();
  const deque = [];
  for (const file of [...entrySet].sort()) {
    const sf = program.getSourceFile(file);
    if (!sf) continue;
    deque.push({ kind: "file", key: `F:${rel(file)}`, file, rel: rel(file), sf, distance: 0, via: [], entry: true });
  }
  const pkgName = (file) => packageOf(path.dirname(file))?.name ?? null;
  while (deque.length) {
    const node = deque.shift();
    for (const e of edgesOf(node)) {
      if (e.kind === "external") { if (e.name) external.add(e.name); continue; }
      if (entrySet.has(e.file)) continue; // anchored: stamped and checked directly
      const distance = node.distance + (e.same ? 0 : 1);
      if (distance > maxDepth) continue;
      const from = pkgName(node.file);
      const to = pkgName(e.file);
      const via = to && to !== from ? [...node.via, to] : node.via;
      const seen = best.get(e.key);
      if (seen && (seen.distance < distance || (seen.distance === distance && seen.via.length <= via.length))) continue;
      const next = { ...e, distance, via };
      best.set(e.key, next);
      if (e.same) deque.unshift(next); else deque.push(next);
    }
  }
  const nodes = [...best.values()].map((n) => n.kind === "file"
    ? { file: n.rel, symbol: null, distance: n.distance, via: n.via }
    : { file: n.rel, symbol: n.name, distance: n.distance, via: n.via,
        hash: sha(n.stmts.map((s) => s.getText()).join("\n")) });
  nodes.sort((a, b) => a.file.localeCompare(b.file) || (a.symbol ?? "").localeCompare(b.symbol ?? ""));
  return { nodes, external: [...external].sort() };
}

const closures = {};
for (const [name, entries] of Object.entries(capabilities)) closures[name] = closure(entries);
process.stdout.write(JSON.stringify({ typescript: ts.version, closures }));
