#!/usr/bin/env node
import { spawnSync } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const skillRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const core = path.join(skillRoot, 'bin', 'archify.mjs');
const example = path.join(skillRoot, 'examples', 'nature-workflow.json');
const MAX_HEIGHT_MM = 170;
const MIN_FONT_PT = 5;
const MAX_FONT_PT = 7;

class FigureError extends Error {
  constructor(message, code = 'archify-figures/internal', details = {}) {
    super(message);
    this.code = code;
    this.details = details;
  }
}

function sha256(text) {
  return createHash('sha256').update(text).digest('hex');
}

function runCore(args) {
  const result = spawnSync(process.execPath, [core, ...args], {
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
    env: { ...process.env, ARCHIFY_UPDATE_CHECK_DISABLED: '1' },
  });
  if (result.error || result.status !== 0) {
    let diagnostics = [];
    try {
      const receipt = JSON.parse(String(result.stdout || '').trim());
      diagnostics = receipt.diagnostics || [];
    } catch {}
    const detail = String(result.stderr || result.stdout || '').trim().slice(0, 4000);
    throw new FigureError(
      result.error?.message || `Archify ${args[0]} failed with exit ${result.status ?? 'unknown'}.`,
      'archify-figures/core-failed',
      { command: args[0], diagnostics, detail },
    );
  }
  return result;
}

function parseOutput(args, name) {
  const index = args.indexOf(name);
  if (index < 0) return undefined;
  const value = args[index + 1];
  if (!value || value.startsWith('--')) throw new FigureError(`${name} needs a value.`, 'archify-figures/arguments');
  args.splice(index, 2);
  return value;
}

function rejectUnknown(args, allowed) {
  const unknown = args.find(value => value.startsWith('--') && !allowed.has(value));
  if (unknown) throw new FigureError(`Unknown option: ${unknown}`, 'archify-figures/arguments');
}

function rootTag(svg) {
  const match = svg.match(/<svg\b[^>]*>/i);
  if (!match) throw new FigureError('The renderer did not emit an SVG root.', 'archify-figures/svg-root');
  return match[0];
}

function setRootAttribute(tag, name, value) {
  const pattern = new RegExp(`(\\s)${name}=(["']).*?\\2`, 'i');
  if (pattern.test(tag)) return tag.replace(pattern, `$1${name}="${value}"`);
  return tag.replace(/\s*>$/, ` ${name}="${value}">`);
}

function journalSvg(source, requestedWidthMm) {
  let svg = source
    .replace(/<style\b[^>]*\bid=(["'])archify-fonts\1[^>]*>[\s\S]*?<\/style>\s*/gi, '')
    .replace(/@font-face\s*\{[^{}]*\}\s*/gi, '')
    .replace(/font-family\s*:\s*[^;}]+/gi, 'font-family: Arial, Helvetica, sans-serif');

  const originalRoot = rootTag(svg);
  const viewBox = originalRoot.match(/\bviewBox=(["'])([^"']+)\1/i);
  if (!viewBox) throw new FigureError('The SVG has no viewBox.', 'archify-figures/view-box');
  const values = viewBox[2].trim().split(/[\s,]+/).map(Number);
  if (values.length !== 4 || values.some(value => !Number.isFinite(value)) || values[2] <= 0 || values[3] <= 0) {
    throw new FigureError('The SVG viewBox is invalid.', 'archify-figures/view-box');
  }
  const [, , sourceWidth, sourceHeight] = values;
  const scale = Math.min(requestedWidthMm / sourceWidth, MAX_HEIGHT_MM / sourceHeight);
  const widthMm = sourceWidth * scale;
  const heightMm = sourceHeight * scale;
  const pointsPerUnit = scale * 72 / 25.4;

  const textTags = [...svg.matchAll(/<text\b[^>]*>/gi)].map(match => match[0]);
  if (!textTags.length) throw new FigureError('The SVG has no editable text elements.', 'archify-figures/text');
  const fontSizes = [];
  for (const tag of textTags) {
    const match = tag.match(/\bfont-size=(["'])([\d.]+)\1/i);
    if (!match) throw new FigureError('A text element has no explicit font-size.', 'archify-figures/text-size');
    fontSizes.push(Number(match[2]) * pointsPerUnit);
  }
  const minFontPt = Math.min(...fontSizes);
  const maxFontPt = Math.max(...fontSizes);
  if (minFontPt < MIN_FONT_PT - 0.01 || maxFontPt > MAX_FONT_PT + 0.01) {
    throw new FigureError(
      `Projected text is ${minFontPt.toFixed(2)}–${maxFontPt.toFixed(2)} pt; Nature figures require ${MIN_FONT_PT}–${MAX_FONT_PT} pt. Simplify or resize the composition.`,
      'archify-figures/font-range',
      { minFontPt, maxFontPt, widthMm, heightMm },
    );
  }
  if (heightMm > MAX_HEIGHT_MM + 0.01) {
    throw new FigureError(`Figure height is ${heightMm.toFixed(2)} mm; the maximum is ${MAX_HEIGHT_MM} mm.`, 'archify-figures/height');
  }
  if (/<image\b/i.test(svg)) throw new FigureError('Journal figures must be vector artwork; the SVG contains an image.', 'archify-figures/raster');
  if (/(?:href|src)=(["'])https?:/i.test(svg)) throw new FigureError('Journal figures must not link external resources.', 'archify-figures/external-resource');
  if (/@font-face|data:font\//i.test(svg)) throw new FigureError('The presentation font was not removed.', 'archify-figures/font-data');

  let updatedRoot = setRootAttribute(originalRoot, 'width', widthMm.toFixed(3));
  updatedRoot = setRootAttribute(updatedRoot, 'height', heightMm.toFixed(3));
  updatedRoot = setRootAttribute(updatedRoot, 'data-archify-figures', 'nature');
  updatedRoot = setRootAttribute(updatedRoot, 'data-figure-width-mm', widthMm.toFixed(3));
  svg = svg.replace(originalRoot, updatedRoot);
  svg = svg.replace(/<\/svg>\s*$/i, '<style>svg text{fill:#000!important}svg *{filter:none!important}</style>\n</svg>');

  return {
    svg,
    metrics: {
      requestedWidthMm,
      widthMm: Number(widthMm.toFixed(3)),
      heightMm: Number(heightMm.toFixed(3)),
      minFontPt: Number(minFontPt.toFixed(3)),
      maxFontPt: Number(maxFontPt.toFixed(3)),
      textElements: textTags.length,
    },
  };
}

function atomicWrite(target, content) {
  const resolved = path.resolve(target);
  fs.mkdirSync(path.dirname(resolved), { recursive: true });
  const temporary = path.join(path.dirname(resolved), `.${path.basename(resolved)}.${process.pid}.${randomUUID()}.tmp`);
  try {
    fs.writeFileSync(temporary, content, { flag: 'wx' });
    fs.renameSync(temporary, resolved);
  } finally {
    fs.rmSync(temporary, { force: true });
  }
  return resolved;
}

function exportJournal(candidate, output, requestedWidthMm) {
  const width = Number(requestedWidthMm);
  if (width !== 89 && width !== 183) throw new FigureError('--width must be 89 or 183.', 'archify-figures/arguments');
  const input = path.resolve(candidate);
  const validation = runCore(['validate', 'workflow', input, '--quality', 'showcase', '--json']);
  const validationReceipt = JSON.parse(validation.stdout);
  if (!validationReceipt.ok) throw new FigureError('Workflow validation failed.', 'archify-figures/validation', validationReceipt);

  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'archify-figures-'));
  try {
    const raw = path.join(temporary, 'workflow.svg');
    const exported = runCore(['export-svg', 'workflow', input, raw, '--theme', 'light', '--preset', 'editorial', '--json']);
    const exportReceipt = JSON.parse(exported.stdout);
    if (!exportReceipt.ok) throw new FigureError('SVG export failed.', 'archify-figures/export', exportReceipt);
    const prepared = journalSvg(fs.readFileSync(raw, 'utf8'), width);
    const target = atomicWrite(output, prepared.svg);
    return {
      schemaVersion: 1,
      ok: true,
      command: 'export',
      input,
      output: target,
      bytes: Buffer.byteLength(prepared.svg),
      sha256: sha256(prepared.svg),
      checks: { validation: true, vector: true, externalResources: false, editableText: true },
      ...prepared.metrics,
    };
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}

function presentation(candidate, outputStem, theme, preset) {
  const input = path.resolve(candidate);
  const stem = path.resolve(outputStem);
  const htmlContent = runRender(input, `${stem}.html`);
  const html = atomicWrite(`${stem}.html`, htmlContent);
  const exported = runCore(['export-svg', 'workflow', input, stem, '--theme', theme, '--preset', preset, '--json']);
  const receipt = JSON.parse(exported.stdout);
  if (!receipt.ok) throw new FigureError('Presentation SVG export failed.', 'archify-figures/presentation', receipt);
  return {
    schemaVersion: 1,
    ok: true,
    command: 'presentation',
    input,
    html,
    outputs: receipt.outputs,
  };
}

function runRender(input, output) {
  runCore(['render', 'workflow', input, output, '--quality', 'showcase']);
  const target = path.resolve(output);
  if (!fs.statSync(target).isFile()) throw new FigureError('The renderer did not write the presentation HTML.', 'archify-figures/presentation');
  return fs.readFileSync(target, 'utf8');
}

function smoke() {
  const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'archify-figures-smoke-'));
  try {
    const receipt = exportJournal(example, path.join(temporary, 'figure.svg'), 183);
    return { ...receipt, smoke: true };
  } finally {
    fs.rmSync(temporary, { recursive: true, force: true });
  }
}

function usage() {
  return [
    'Usage:',
    '  node bin/archify-figure.mjs export <candidate.json> <figure.svg> --width 89|183 [--json]',
    '  node bin/archify-figure.mjs presentation <candidate.json> <stem> [--theme both|light|dark] [--preset classic|signal-flow|blueprint|editorial] [--json]',
    '  node bin/archify-figure.mjs smoke [--json]',
  ].join('\n');
}

async function main() {
  const [command, ...args] = process.argv.slice(2);
  const json = args.includes('--json');
  const clean = args.filter(value => value !== '--json');
  try {
    if (Number(process.versions.node.split('.')[0]) < 18) throw new FigureError('Node 18 or newer is required.', 'archify-figures/node');
    let receipt;
    if (command === 'export') {
      rejectUnknown(clean, new Set(['--width']));
      const width = parseOutput(clean, '--width');
      const [candidate, output, ...extra] = clean;
      if (!candidate || !output || extra.length) throw new FigureError(usage(), 'archify-figures/arguments');
      receipt = exportJournal(candidate, output, width);
    } else if (command === 'presentation') {
      rejectUnknown(clean, new Set(['--theme', '--preset']));
      const theme = parseOutput(clean, '--theme') || 'both';
      const preset = parseOutput(clean, '--preset') || 'editorial';
      const [candidate, output, ...extra] = clean;
      if (!candidate || !output || extra.length) throw new FigureError(usage(), 'archify-figures/arguments');
      if (!['both', 'light', 'dark'].includes(theme)) throw new FigureError('Unknown theme.', 'archify-figures/arguments');
      if (!['classic', 'signal-flow', 'blueprint', 'editorial'].includes(preset)) throw new FigureError('Unknown preset.', 'archify-figures/arguments');
      receipt = presentation(candidate, output, theme, preset);
    } else if (command === 'smoke') {
      if (clean.length) throw new FigureError(usage(), 'archify-figures/arguments');
      receipt = smoke();
    } else if (command === 'help' || command === '--help' || !command) {
      console.log(usage());
      return;
    } else {
      throw new FigureError(usage(), 'archify-figures/arguments');
    }
    if (json) console.log(JSON.stringify(receipt, null, 2));
    else if (receipt.command === 'export') console.log(`${receipt.output} (${receipt.widthMm} × ${receipt.heightMm} mm, ${receipt.minFontPt}–${receipt.maxFontPt} pt)`);
    else if (receipt.command === 'presentation') console.log(receipt.html);
    else console.log(`archify-figures smoke: ok (${receipt.widthMm} × ${receipt.heightMm} mm, ${receipt.minFontPt}–${receipt.maxFontPt} pt)`);
  } catch (error) {
    const failure = error instanceof FigureError
      ? { schemaVersion: 1, ok: false, code: error.code, error: error.message, ...error.details }
      : { schemaVersion: 1, ok: false, code: 'archify-figures/internal', error: error.message };
    if (json) console.log(JSON.stringify(failure, null, 2));
    else console.error(failure.error);
    process.exitCode = 1;
  }
}

main();
