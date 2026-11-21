// Profile Enhancement Script Template for Clash Verge
//
// Reference copy of the live script enhancement for the active profile:
//   ~/Library/Application Support/io.github.clash-verge-rev.clash-verge-rev/profiles/<uid>.js
// `clash/` is chezmoi-ignored, so this file is never applied to $HOME.
//
// Why the fallback lives here and not in the rule editor:
//   Clash Verge applies a profile's enhancements in this order:
//     rules/groups editor -> merge config -> script
//   (upstream main, src-tauri/src/enhance/mod.rs lines 853-892: the profile
//   script is applied after the rule/group editing and the merge)
//   The rule editor appends after the subscription's own rules, and a
//   subscription ends with its own catch-all, so a catch-all added there can
//   never match. The editor also deletes rules by their exact string, and the
//   subscription names its own catch-all group, so the catch-all cannot be
//   removed by name either. The script runs last and can do both: it finds the
//   catch-all by its rule type and replaces it with the owned fallback group.
//
// The invariant: the effective rules carry exactly one catch-all, it is the
// final rule, and it routes to the owned group (兜底) defined by
// clash/groups-enhancement.yaml.
//
// Groups: PROXY, 🚀节点选择, ♻️自动选择, 🐟漏网之鱼, 🎬媒体解锁, 🤖AI网站,
//   🛑广告拦截, 🇯🇵日本节点, 🇸🇬狮城节点, 🇺🇸美国节点

var FALLBACK_GROUP = '兜底';

/**
 * The rule type of a rule string: the token before the first comma, trimmed.
 *
 * The pinned Mihomo accepts a rule whose type carries surrounding spaces
 * ("MATCH ,DIRECT") in config-test mode, so the type token is compared after
 * trimming rather than by prefix. Comparing the whole token keeps a rule
 * whose type merely resembles MATCH ("MATCH-SET", ...) out of the catch-all
 * set, so such a rule is preserved like any other specific rule.
 */
function ruleType(rule) {
  if (typeof rule !== 'string') {
    return '';
  }
  var text = rule.trim();
  var comma = text.indexOf(',');
  var type = comma === -1 ? text : text.slice(0, comma);
  return type.trim().toUpperCase();
}

function isCatchAll(rule) {
  return ruleType(rule) === 'MATCH';
}

function hasGroup(config, name) {
  if (!Array.isArray(config['proxy-groups'])) {
    return false;
  }
  for (var index = 0; index < config['proxy-groups'].length; index += 1) {
    var group = config['proxy-groups'][index];
    if (group && group.name === name) {
      return true;
    }
  }
  return false;
}

function main(config, profileName) {
  if (!config) {
    return config;
  }

  // A profile without a rule list is handled as an empty list: the owned
  // catch-all is still the only final rule, so the traffic keeps one
  // predictable route. The recipe always publishes a rule list (the rule
  // editor writes one), but the script does not rely on that.
  var rules = Array.isArray(config.rules) ? config.rules : [];

  // A rule that names a group the config does not define makes Mihomo refuse
  // the whole config, so the vendor's catch-all is kept instead.
  if (!hasGroup(config, FALLBACK_GROUP)) {
    console.warn('the ' + FALLBACK_GROUP + ' group is missing; the catch-all is left alone');
    return config;
  }

  var kept = [];
  for (var index = 0; index < rules.length; index += 1) {
    if (isCatchAll(rules[index])) {
      continue;
    }
    // Every other rule is kept verbatim, in its original order.
    kept.push(rules[index]);
  }

  kept.push('MATCH,' + FALLBACK_GROUP);
  config.rules = kept;
  return config;
}
