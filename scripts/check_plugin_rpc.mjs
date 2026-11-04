import ts from 'typescript';
import { readFileSync, readdirSync, existsSync } from 'node:fs';
import path, { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import process from 'node:process';
import console from 'node:console';
import { parseArgs } from 'node:util';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const slash = (path) => path.replaceAll('\\', '/');

/** Whether a source belongs to this directory, using the selected platform's paths. */
export function isWithinDirectory(directory, source, paths = path) {
  const child = paths.relative(directory, source);
  return !paths.isAbsolute(child) && child !== '..' && !child.startsWith(`..${paths.sep}`);
}

/** Finite string values inferred by TypeScript, including template-literal unions. */
export function finiteStrings(type) {
  if (type.isStringLiteral()) return [type.value];
  if (type.isUnion()) {
    const parts = type.types.map(finiteStrings);
    if (parts.every(Boolean)) return [...new Set(parts.flat())];
  }
  return null;
}

function lane(declaration) {
  if (!declaration || !/\/rpc(?:\.d)?\.ts$/.test(slash(declaration.getSourceFile().fileName))) return null;
  const name = declaration.name?.getText();
  if (!['call', 'handle', 'dependency', 'list'].includes(name)) return null;
  for (let node = declaration.parent; node; node = node.parent) {
    if (ts.isPropertySignature(node) && node.name.getText() === 'services') return name === 'list' ? 'service-contract' : 'services';
    if (ts.isPropertySignature(node) && node.name.getText() === 'background') return 'background';
    if (ts.isTypeAliasDeclaration(node) && ['PluginPeer', 'PluginRpcClient'].includes(node.name.text)) return name === 'handle' ? 'register' : name === 'dependency' ? 'dependency' : 'backend';
  }
  return null;
}

/** Validate the finite names of actual SDK client calls against backend and background providers. */
export function checkPluginRpc({ root = ROOT, plugin: selectedPlugin } = {}) {
  const config = ts.readConfigFile(join(root, 'plugins/tsconfig.json'), ts.sys.readFile);
  if (config.error) throw new Error(ts.flattenDiagnosticMessageText(config.error.messageText, '\n'));
  const parsed = ts.parseJsonConfigFileContent(config.config, ts.sys, join(root, 'plugins'));
  parsed.options.paths = {
    '@yinfengwindy/shiori-sdk': [join(root, 'packages/sdk/src/index.ts')],
    '@yinfengwindy/shiori-sdk/*': [join(root, 'packages/sdk/src/*')],
  };
  const directories = readdirSync(join(root, 'plugins')).map((name) => join(root, 'plugins', name)).filter((directory) => existsSync(join(directory, 'manifest.yaml')));
  if (selectedPlugin && !directories.includes(resolve(selectedPlugin))) directories.push(resolve(selectedPlugin));
  // Include plugin-root frontend entries as well as the conventional ui/background directories.
  const extra = directories.flatMap((directory) => ts.sys.readDirectory(directory, ['.ts', '.tsx'], ['**/node_modules/**', '**/dist/**']));
  const program = ts.createProgram([...parsed.fileNames, ...extra], parsed.options);
  const checker = program.getTypeChecker();
  const contracts = new Map();
  const owners = new Map();
  for (const directory of directories) {
    const path = join(directory, 'rpc-contract.generated.json');
    const contract = JSON.parse(readFileSync(path, 'utf8').replace(/^\uFEFF/, ''));
    contracts.set(contract.plugin_id, contract);
    owners.set(directory, contract.plugin_id);
  }
  const background = new Map();
  const calls = [];
  const errors = [];
  const selectedId = selectedPlugin ? owners.get(resolve(selectedPlugin)) : undefined;
  const located = (node, message, plugin) => {
    if (selectedId && plugin !== selectedId) return;
    const source = node.getSourceFile();
    const { line, character } = source.getLineAndCharacterOfPosition(node.getStart());
    errors.push(`${relative(root, source.fileName)}:${line + 1}:${character + 1}: ${message}`);
  };
  const visitedHelpers = new Set();
  function visit(node, plugin) {
      if (ts.isCallExpression(node)) {
        const declaration = checker.getResolvedSignature(node)?.declaration;
        const kind = lane(declaration);
        if (kind) {
          const argument = node.arguments[kind === 'services' ? 1 : 0];
          const names = argument ? finiteStrings(checker.getTypeAtLocation(argument)) : null;
          if (!names) located(node, `${kind} method must have a finite string-literal type`, plugin);
          else if (kind === 'register') {
            if (!background.has(plugin)) background.set(plugin, new Set());
            for (const name of names) background.get(plugin).add(name);
          } else calls.push({ node, argument, names, kind, plugin });
        } else visitHelper(declaration, plugin);
      } else if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
        let symbol = checker.getSymbolAtLocation(node.tagName);
        if (symbol?.flags & ts.SymbolFlags.Alias) symbol = checker.getAliasedSymbol(symbol);
        visitHelper(symbol?.valueDeclaration, plugin);
      }
      ts.forEachChild(node, (child) => visit(child, plugin));
  }
  function visitHelper(declaration, plugin) {
    if (declaration && slash(declaration.getSourceFile().fileName).includes('/packages/sdk/src/') && declaration.body) {
      const identity = `${plugin}:${declaration.getSourceFile().fileName}:${declaration.pos}`;
      if (!visitedHelpers.has(identity)) {
        visitedHelpers.add(identity);
        visit(declaration.body, plugin);
      }
    }
  }
  for (const source of program.getSourceFiles()) {
    if (/\.(test|generated)\./.test(source.fileName) || source.isDeclarationFile) continue;
    const owner = [...owners].find(([directory]) => isWithinDirectory(directory, source.fileName));
    if (owner) {
      visit(source, owner[1]);
    }
  }
  function memberName(expression) {
    if (ts.isPropertyAccessExpression(expression)) return expression.name.text;
    if (ts.isElementAccessExpression(expression)) {
      const names = finiteStrings(checker.getTypeAtLocation(expression.argumentExpression));
      if (names?.length === 1) return names[0];
    }
    return null;
  }
  function constantInitializer(declaration) {
    return declaration && ts.isVariableDeclaration(declaration) && declaration.parent.flags & ts.NodeFlags.Const
      ? declaration.initializer : undefined;
  }
  function targetPlugin(node, plugin) {
    const seen = new Set();
    // Only follow literal members and local const aliases. An unresolved peer must
    // not silently inherit the caller's method set.
    function resolveTarget(expression, isCallee = false) {
      if (!expression || seen.has(expression)) return null;
      seen.add(expression);
      if (ts.isParenthesizedExpression(expression) || ts.isNonNullExpression(expression) || ts.isAwaitExpression(expression)) {
        return resolveTarget(expression.expression, isCallee);
      }
      if (!isCallee && checker.getTypeAtLocation(expression).getProperty('dependency')) return plugin;
      if (!isCallee && ts.isCallExpression(expression) && lane(checker.getResolvedSignature(expression)?.declaration) === 'dependency') {
        const ids = expression.arguments[0] && finiteStrings(checker.getTypeAtLocation(expression.arguments[0]));
        return ids?.length === 1 ? ids[0] : null;
      }
      const member = memberName(expression);
      if ((isCallee && member === 'call') || (!isCallee && member === 'background')) {
        return resolveTarget(expression.expression);
      }
      if (ts.isIdentifier(expression)) {
        const declaration = checker.getSymbolAtLocation(expression)?.valueDeclaration;
        if (declaration && ts.isBindingElement(declaration)) {
          const member = (declaration.propertyName ?? declaration.name).getText().replace(/^['"]|['"]$/g, '');
          if ((isCallee && member === 'call') || (!isCallee && member === 'background')) {
            return resolveTarget(constantInitializer(declaration.parent.parent));
          }
        } else return resolveTarget(constantInitializer(declaration), isCallee);
      }
      return null;
    }
    const target = resolveTarget(node.expression, true);
    if (!target) located(node, 'RPC target cannot be resolved to the owning client or one declared dependency', plugin);
    return target;
  }
  const selectedCalls = calls.filter(({ plugin }) => !selectedId || plugin === selectedId);
  for (const { node, argument, names, kind, plugin } of selectedCalls) {
    const target = ['backend', 'background'].includes(kind) ? targetPlugin(node, plugin) : plugin;
    if (!target) continue;
    let allowed;
    if (kind === 'dependency') {
      // YAML is parsed by the Python generator; use its exact manifest declarations.
      allowed = new Set(contracts.get(plugin)?.dependencies ?? []);
    } else if (kind === 'background') allowed = background.get(target) ?? new Set();
    else if (kind === 'service-contract') allowed = new Set([...contracts.values()].flatMap((contract) => contract.services.map((service) => service.contract)));
    else if (kind === 'services') {
      const service = node.arguments[0];
      const type = checker.getTypeAtLocation(service);
      const ids = ['plugin_id', 'service_id'].map((key) => {
        if (ts.isObjectLiteralExpression(service)) {
          const field = service.properties.find((entry) => ts.isPropertyAssignment(entry) && entry.name.getText() === key);
          if (field) return finiteStrings(checker.getTypeAtLocation(field.initializer));
        }
        const property = type.getProperty(key);
        return property ? finiteStrings(checker.getTypeOfSymbolAtLocation(property, service)) : null;
      });
      const sources = ids[0]?.length === 1 ? [contracts.get(ids[0][0])] : [...contracts.values()];
      // A persisted PluginServiceReference has no static contract tag. In that case
      // this proves only that a service declares the method; the runtime validates
      // the selected provider. Literal references are checked against that service.
      allowed = new Set(sources.filter(Boolean).flatMap((c) => c.services.filter((entry) => !ids[1] || ids[1].includes(entry.service_id)).flatMap((entry) => entry.methods)));
    } else allowed = new Set(contracts.get(target)?.methods ?? []);
    for (const name of names) if (!allowed.has(name)) located(argument, `${kind} method ${JSON.stringify(name)} has no provider in ${target}`, plugin);
  }
  return { errors, checked: selectedCalls.length, backgrounds: Object.fromEntries([...background].map(([key, value]) => [key, [...value].sort()])) };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({ options: { plugin: { type: 'string' } } });
  const result = checkPluginRpc({ plugin: values.plugin });
  if (result.errors.length) { console.error(result.errors.join('\n')); process.exitCode = 1; }
  console.log(`${result.checked} plugin RPC/backend/background/service calls checked`);
}
