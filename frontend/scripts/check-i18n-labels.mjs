import fs from 'node:fs';
import path from 'node:path';
import ts from 'typescript';

const sourceRoot = path.resolve('src');
const han = /\p{Script=Han}/u;
const words = /[\p{L}\p{N}]/u;
const userFacingAttributes = new Set([
  'aria-label',
  'aria-description',
  'placeholder',
  'title',
]);
const allowedFixedUiLiterals = new Set(['Floris', 'PDF', 'arXiv']);

// These literals are protocol/content parsers, provider defaults, prompt
// delimiters, or single-character brand icons. They are not fixed UI labels.
const allowedRuntimeLiterals = new Map([
  ['features/maps/controller/useMapsController.ts', ['全国']],
  ['features/maps/model/client.ts', ['全国']],
  ['features/settings/controller/useSettingsController.ts', ['全国']],
  ['features/workspace/controller/useWorkspaceController.ts', ['全国']],
  ['services/conversation.ts', [
    '地点已经核实，请点击下方按钮显示地点',
    '地点已经过真实地点服务核实',
    '腾讯会议确认卡已准备好',
    '日程变更确认卡已准备好',
    '图片任务已准备好',
    '新对话',
    '历史对话',
  ]],
  ['features/chat/view/MessageBubble.tsx', ['生成图片', '绘制', '已识别为论文']],
]);

// These errors are developer invariants or private control-flow sentinels;
// callers replace them with localized copy before anything reaches the UI.
const allowedInternalErrors = new Map([
  ['store/appState.ts', [
    'useAppState must be used within AppProvider',
    'useAppDispatch must be used within AppProvider',
  ]],
  ['features/chat/controller/useMessageBubbleController.ts', [
    'png unavailable',
    'copy failed',
  ]],
  ['shared/auth/avatarCache.ts', [
    'Avatar could not be decoded',
  ]],
]);

function sourceFiles(directory) {
  return fs.readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const absolute = path.join(directory, entry.name);
    if (entry.isDirectory()) return sourceFiles(absolute);
    if (!/\.(?:ts|tsx)$/.test(entry.name) || /\.test\.(?:ts|tsx)$/.test(entry.name)) return [];
    return [absolute];
  });
}

function literalText(node, sourceFile) {
  if (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node) || ts.isJsxText(node)) {
    return node.text;
  }
  if (ts.isTemplateExpression(node)) {
    return node.getText(sourceFile).slice(1, -1);
  }
  return '';
}

function isDirectUserFacingLiteral(node) {
  if (ts.isJsxText(node)) return words.test(node.text.trim());

  if (ts.isStringLiteral(node) && ts.isJsxAttribute(node.parent)) {
    return userFacingAttributes.has(node.parent.name.getText());
  }

  if (ts.isStringLiteral(node) && ts.isCallExpression(node.parent)) {
    const expression = node.parent.expression;
    if (!ts.isPropertyAccessExpression(expression)) return false;
    const owner = expression.expression.getText();
    return owner === 'MessagePlugin' && ['success', 'error', 'warning', 'info'].includes(expression.name.text);
  }

  return false;
}

function isToastCall(node) {
  if (!ts.isCallExpression(node) || !ts.isPropertyAccessExpression(node.expression)) return false;
  return node.expression.expression.getText() === 'MessagePlugin'
    && ['success', 'error', 'warning', 'info'].includes(node.expression.name.text);
}

function usesTranslation(node) {
  let translated = false;
  const inspect = (child) => {
    if (
      ts.isCallExpression(child)
      && (
        child.expression.getText() === 't'
        || child.expression.getText() === 'translate'
      )
    ) translated = true;
    if (!translated) ts.forEachChild(child, inspect);
  };
  inspect(node);
  return translated;
}

const failures = [];
for (const absolute of sourceFiles(sourceRoot)) {
  const relative = path.relative(sourceRoot, absolute).split(path.sep).join('/');
  if (relative === 'i18n.tsx') continue;
  const source = fs.readFileSync(absolute, 'utf8');
  const sourceFile = ts.createSourceFile(
    absolute,
    source,
    ts.ScriptTarget.Latest,
    true,
    absolute.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
  );
  const allowed = allowedRuntimeLiterals.get(relative) || [];
  const allowedErrors = allowedInternalErrors.get(relative) || [];
  const visit = (node) => {
    if (isToastCall(node) && (!node.arguments[0] || !usesTranslation(node.arguments[0]))) {
      const { line, character } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
      failures.push(`${relative}:${line + 1}:${character + 1} Toast must use t(...) or translate(...)`);
    }
    if (
      ts.isNewExpression(node)
      && node.expression.getText(sourceFile) === 'Error'
      && node.arguments?.[0]
      && !usesTranslation(node.arguments[0])
    ) {
      const errorText = literalText(node.arguments[0], sourceFile).trim();
      if (errorText && !allowedErrors.some((fragment) => errorText.includes(fragment))) {
        const { line, character } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
        failures.push(`${relative}:${line + 1}:${character + 1} Error must use t(...) or translate(...)`);
      }
    }
    const text = literalText(node, sourceFile);
    const trimmed = text.trim();
    const untranslatedChinese = text && han.test(text) && !allowed.some((fragment) => text.includes(fragment));
    const directFixedUi = text
      && isDirectUserFacingLiteral(node)
      && !allowedFixedUiLiterals.has(trimmed);
    if (untranslatedChinese || directFixedUi) {
      const { line, character } = sourceFile.getLineAndCharacterOfPosition(node.getStart(sourceFile));
      failures.push(`${relative}:${line + 1}:${character + 1} ${JSON.stringify(trimmed.slice(0, 120))}`);
    }
    ts.forEachChild(node, visit);
  };
  visit(sourceFile);
}

if (failures.length) {
  process.stderr.write([
    'Found user-visible fixed literals outside src/i18n.tsx.',
    'Move fixed copy into the five-language catalog, or document a non-UI parser literal in this audit script.',
    ...failures,
    '',
  ].join('\n'));
  process.exit(1);
}

process.stdout.write('i18n label audit passed\n');
