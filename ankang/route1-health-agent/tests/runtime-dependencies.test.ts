import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

test('runtime transitive source closure has no React, TSX, platform UI, PeerJS or Home Twin dependencies', () => {
  const root = path.resolve(__dirname, '../..');
  const visited = new Set<string>();
  const options: ts.CompilerOptions = { moduleResolution: ts.ModuleResolutionKind.Node10 };
  function walk(file: string) {
    if (visited.has(file)) return;
    visited.add(file);
    assert.ok(!/\.tsx$|[/\\](?:hooks|components|adapters|agent-tools|config|route2)[/\\]/i.test(file), file);
    const source = ts.createSourceFile(file, readFileSync(file, 'utf8'), ts.ScriptTarget.Latest, true);
    function dependency(specifier: string) {
      assert.ok(specifier.startsWith('.'), `Runtime must have no external imports: ${specifier}`);
      const resolved = ts.resolveModuleName(specifier, file, options, ts.sys).resolvedModule;
      assert.ok(resolved, specifier);
      walk(resolved.resolvedFileName);
    }
    function visit(node: ts.Node) {
      if (
        (ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) &&
        node.moduleSpecifier &&
        ts.isStringLiteral(node.moduleSpecifier)
      )
        dependency(node.moduleSpecifier.text);
      if (
        ts.isCallExpression(node) &&
        (node.expression.kind === ts.SyntaxKind.ImportKeyword ||
          (ts.isIdentifier(node.expression) && node.expression.text === 'require'))
      ) {
        assert.ok(node.arguments[0] && ts.isStringLiteral(node.arguments[0]), 'Nonliteral dynamic imports forbidden');
        dependency((node.arguments[0] as ts.StringLiteral).text);
      }
      ts.forEachChild(node, visit);
    }
    visit(source);
  }
  walk(path.join(root, 'src/runtime/index.ts'));
  assert.ok(visited.size >= 25, 'Check transitive domain imports, not only the facade');
  console.log(`Runtime source closure: ${visited.size} TypeScript modules; no external imports`);
});
