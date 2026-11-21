// Offline regression for the desktop Clash Verge fallback rule.
//
// The per-profile rule editor appends after the subscription's own rules, and
// a subscription ends with its own catch-all, so a catch-all added by the
// editor can never match. The Script enhancement runs last in Clash Verge's
// pipeline (rules/groups -> merge -> script), so it owns the final catch-all
// and replaces the vendor's one by rule type instead of by name.
//
// Run: node --test clash/tests/

import { test } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const clashDir = join(dirname(fileURLToPath(import.meta.url)), "..");
const scriptPath = join(clashDir, "script-enhancement.js");
const rulesPath = join(clashDir, "rules-enhancement.yaml");
const groupsPath = join(clashDir, "groups-enhancement.yaml");

// The owned fallback group, as clash/groups-enhancement.yaml defines it.
const FALLBACK_GROUP = "兜底";

// Vendor catch-alls differ per subscription; none of them may be guessed.
const VENDOR_CATCH_ALLS = [
  "MATCH,🐟漏网之鱼",
  "MATCH,DIRECT",
  "MATCH,Final",
  "MATCH,🚀节点选择",
  // The pinned Mihomo accepts a space before the comma in config-test mode,
  // so the rule type token is compared after trimming.
  "MATCH ,DIRECT",
];

const VENDOR_SPECIFIC = [
  "DOMAIN-SUFFIX,google.com,🚀节点选择",
  "RULE-SET,gfw,PROXY",
  "GEOIP,CN,DIRECT",
  "RULE-SET,private,DIRECT",
];

/**
 * The rule type token of a rule string: the text before the first comma,
 * trimmed and compared case-insensitively. The whole token is compared, so a
 * rule whose type only resembles MATCH stays a specific rule.
 */
const ruleType = (rule) => {
  if (typeof rule !== "string") {
    return "";
  }
  const text = rule.trim();
  const comma = text.indexOf(",");
  return (comma === -1 ? text : text.slice(0, comma)).trim().toUpperCase();
};

const isCatchAll = (rule) => ruleType(rule) === "MATCH";

/**
 * Read the rule editor's three lists out of its YAML.
 *
 * The editor file is a flat mapping of three lists of quoted strings, so a
 * line reader is enough and keeps the test free of a YAML dependency.
 */
function readRuleEditor(file) {
  const editor = { prepend: [], append: [], delete: [] };
  let key = null;

  for (const line of readFileSync(file, "utf8").split("\n")) {
    const top = /^([a-z-]+):\s*(.*)$/.exec(line);
    if (top) {
      key = top[1];
      editor[key] = [];
      continue;
    }
    const item = /^\s+-\s+"([^"]*)"\s*$/.exec(line);
    if (item && key && editor[key]) {
      editor[key].push(item[1]);
    }
  }

  return editor;
}

/** The group names the groups enhancement declares. */
function readGroupNames(file) {
  const text = readFileSync(file, "utf8");
  return [...text.matchAll(/^\s*name:\s*'([^']*)'/gm)].map((match) => match[1]);
}

/**
 * Load the profile's script enhancement the way Clash Verge does: the file
 * body is evaluated and its `main` entry is called with the config.
 */
function loadScriptMain() {
  let source;
  try {
    source = readFileSync(scriptPath, "utf8");
  } catch {
    return null;
  }
  return new Function(`${source}\nreturn main;`)();
}

/**
 * Apply the rule editor the way Clash Verge applies it
 * (src-tauri/src/enhance/seq.rs): prepend, then the kept rules, then append,
 * with delete removing whole rules by their exact string.
 */
function applyRuleEditor(config, editor) {
  const rules = Array.isArray(config.rules) ? config.rules : [];
  const kept = rules.filter((rule) => !editor.delete.includes(rule));
  config.rules = [...editor.prepend, ...kept, ...editor.append];
  return config;
}

/** The effective rules of a profile with the given vendor rules. */
function effectiveRules(vendorRules) {
  const editor = readRuleEditor(rulesPath);
  let config = applyRuleEditor(
    {
      rules: [...vendorRules],
      "proxy-groups": [{ name: FALLBACK_GROUP, type: "fallback", proxies: ["us"] }],
    },
    editor,
  );

  const main = loadScriptMain();
  if (main) {
    config = main(config, "test-profile");
  }

  return config.rules;
}

test("the profile script enhancement exists and exposes main", () => {
  assert.ok(
    readFileSync(scriptPath, "utf8").includes("function main("),
    "clash/script-enhancement.js must define the script entry Clash Verge calls",
  );
});

test("the rule editor carries no catch-all of its own", () => {
  const editor = readRuleEditor(rulesPath);

  for (const rule of [...editor.prepend, ...editor.append]) {
    assert.ok(
      !isCatchAll(rule),
      `the editor must not carry the catch-all (${rule}); it would sit behind the vendor's own MATCH`,
    );
  }
  assert.ok(editor.prepend.length > 0, "the editor still owns the personal and managed rules");
  assert.ok(
    editor.prepend.includes("DOMAIN-SUFFIX,aihot.news,PROXY") &&
      editor.prepend.includes("GEOIP,CN,DIRECT"),
    "the editor's own rules must be read whole",
  );
});

test("the owned fallback is the single final MATCH rule", () => {
  for (const catchAll of VENDOR_CATCH_ALLS) {
    const rules = effectiveRules([...VENDOR_SPECIFIC, catchAll]);
    const catchAlls = rules.filter(isCatchAll);

    assert.equal(catchAlls.length, 1, `expected one catch-all for ${catchAll}, got ${catchAlls.length}`);
    assert.equal(
      rules[rules.length - 1],
      catchAlls[0],
      `the catch-all must be the final rule for ${catchAll}`,
    );
    assert.equal(catchAlls[0], `MATCH,${FALLBACK_GROUP}`, `the catch-all must be the owned one for ${catchAll}`);
  }
});

test("every specific vendor and managed rule is kept in order", () => {
  const editor = readRuleEditor(rulesPath);
  // A catch-all in the middle of the vendor's list would make the rules after
  // it unreachable, so it is removed as well.
  const vendor = [...VENDOR_SPECIFIC, "MATCH,🐟漏网之鱼", "DOMAIN-SUFFIX,late.example,DIRECT"];
  const rules = effectiveRules(vendor);
  const specific = rules.filter((rule) => !isCatchAll(rule));

  assert.deepEqual(specific, [...editor.prepend, ...VENDOR_SPECIFIC, "DOMAIN-SUFFIX,late.example,DIRECT"]);
});

test("the script is idempotent", () => {
  const main = loadScriptMain();
  assert.ok(main, "the profile script enhancement must exist");

  const editor = readRuleEditor(rulesPath);
  const once = main(
    applyRuleEditor(
      {
        rules: [...VENDOR_SPECIFIC, "MATCH,🐟漏网之鱼"],
        "proxy-groups": [{ name: FALLBACK_GROUP, type: "fallback", proxies: ["us"] }],
      },
      editor,
    ),
    "test-profile",
  );
  const twice = main(JSON.parse(JSON.stringify(once)), "test-profile");

  assert.deepEqual(twice.rules, once.rules);
});

test("a catch-all spelled with a space before the comma is replaced", () => {
  const editor = readRuleEditor(rulesPath);
  const config = applyRuleEditor(
    {
      rules: [...VENDOR_SPECIFIC, "MATCH ,DIRECT"],
      "proxy-groups": [{ name: FALLBACK_GROUP, type: "fallback", proxies: ["us"] }],
    },
    editor,
  );

  const result = loadScriptMain()(config, "test-profile");
  const catchAlls = result.rules.filter(isCatchAll);

  assert.equal(catchAlls.length, 1, "the spaced catch-all must be replaced, not kept");
  assert.equal(catchAlls[0], `MATCH,${FALLBACK_GROUP}`);
  assert.ok(
    !result.rules.includes("MATCH ,DIRECT"),
    "the vendor's spaced catch-all must not survive",
  );
});

test("a rule whose type only resembles MATCH is preserved in order", () => {
  const editor = readRuleEditor(rulesPath);
  const lookalike = "MATCH-SET,example.com,DIRECT";
  const config = applyRuleEditor(
    {
      rules: [...VENDOR_SPECIFIC, lookalike, "MATCH,🐟漏网之鱼"],
      "proxy-groups": [{ name: FALLBACK_GROUP, type: "fallback", proxies: ["us"] }],
    },
    editor,
  );

  const result = loadScriptMain()(config, "test-profile");

  assert.ok(result.rules.includes(lookalike), "a non-MATCH type must not be taken for a catch-all");
  assert.deepEqual(
    result.rules.filter((rule) => !isCatchAll(rule)),
    [...editor.prepend, ...VENDOR_SPECIFIC, lookalike],
  );
  assert.equal(result.rules[result.rules.length - 1], `MATCH,${FALLBACK_GROUP}`);
});

test("a profile without a rule list gets the owned catch-all", () => {
  const main = loadScriptMain();
  assert.ok(main, "the profile script enhancement must exist");

  const result = main(
    { "proxy-groups": [{ name: FALLBACK_GROUP, type: "fallback", proxies: ["us"] }] },
    "test-profile",
  );

  assert.deepEqual(result.rules, [`MATCH,${FALLBACK_GROUP}`]);
});

test("the fallback group the script targets is declared by the groups enhancement", () => {
  assert.ok(
    readGroupNames(groupsPath).includes(FALLBACK_GROUP),
    `the groups enhancement must declare the ${FALLBACK_GROUP} group the script routes to`,
  );
});

test("the rules stay untouched when the owned group is missing", () => {
  const main = loadScriptMain();
  assert.ok(main, "the profile script enhancement must exist");

  const editor = readRuleEditor(rulesPath);
  const config = applyRuleEditor(
    { rules: [...VENDOR_SPECIFIC, "MATCH,🐟漏网之鱼"], "proxy-groups": [] },
    editor,
  );
  const result = main(config, "test-profile");

  assert.deepEqual(result.rules, config.rules, "a rule pointing at a missing group would break the config");
});
