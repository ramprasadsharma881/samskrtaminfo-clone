/* =========================================================================
   लिपि · script conversion

   The original site pulled in the Aksharamukha web plugin from a CDN on every
   page to offer script conversion. The school clearly cares about this — it
   publishes each stotra separately in Devanāgarī, Telugu and IAST — so the
   feature stays, but it is served from here instead of a third party: no
   external request, works offline, and converts the page instantly.

   Scope: Devanāgarī → Telugu and Devanāgarī → IAST. Devanāgarī is the source
   of truth; the original text of every node is kept so switching back is
   lossless.
   ========================================================================= */
(function (global) {
  "use strict";

  /* ---- Devanāgarī → Telugu -------------------------------------------- */
  /* Both are Brahmic abugidas with the same structure, so a codepoint map is
     enough — inherent vowels, matras and virama all carry across directly.
     Note ए/ओ are the LONG mid vowels: Telugu spells those ఏ/ఓ, not ఎ/ఒ. */
  var TE = {
    "अ": "అ", "आ": "ఆ", "इ": "ఇ", "ई": "ఈ", "उ": "ఉ", "ऊ": "ఊ",
    "ऋ": "ఋ", "ॠ": "ౠ", "ऌ": "ఌ", "ॡ": "ౡ",
    "ए": "ఏ", "ऐ": "ఐ", "ओ": "ఓ", "औ": "ఔ",
    "क": "క", "ख": "ఖ", "ग": "గ", "घ": "ఘ", "ङ": "ఙ",
    "च": "చ", "छ": "ఛ", "ज": "జ", "झ": "ఝ", "ञ": "ఞ",
    "ट": "ట", "ठ": "ఠ", "ड": "డ", "ढ": "ఢ", "ण": "ణ",
    "त": "త", "थ": "థ", "द": "ద", "ध": "ధ", "न": "న",
    "प": "ప", "फ": "ఫ", "ब": "బ", "भ": "భ", "म": "మ",
    "य": "య", "र": "ర", "ल": "ల", "व": "వ",
    "श": "శ", "ष": "ష", "स": "స", "ह": "హ", "ळ": "ళ",
    "ा": "ా", "ि": "ి", "ी": "ీ", "ु": "ు", "ू": "ూ",
    "ृ": "ృ", "ॄ": "ౄ", "ॢ": "ౢ", "ॣ": "ౣ",
    "े": "ే", "ै": "ై", "ो": "ో", "ौ": "ౌ",
    "्": "్", "ं": "ం", "ः": "ః", "ँ": "ఁ", "ऽ": "ఽ",
    "०": "౦", "१": "౧", "२": "౨", "३": "౩", "४": "౪",
    "५": "౫", "६": "౬", "७": "౭", "८": "౮", "९": "౯"
  };

  /* ---- Devanāgarī → IAST ---------------------------------------------- */
  var IAST_VOWEL = {
    "अ": "a", "आ": "ā", "इ": "i", "ई": "ī", "उ": "u", "ऊ": "ū",
    "ऋ": "ṛ", "ॠ": "ṝ", "ऌ": "ḷ", "ॡ": "ḹ",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au"
  };
  var IAST_MATRA = {
    "ा": "ā", "ि": "i", "ी": "ī", "ु": "u", "ू": "ū",
    "ृ": "ṛ", "ॄ": "ṝ", "ॢ": "ḷ", "ॣ": "ḹ",
    "े": "e", "ै": "ai", "ो": "o", "ौ": "au"
  };
  var IAST_CONS = {
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ṅ",
    "च": "c", "छ": "ch", "ज": "j", "झ": "jh", "ञ": "ñ",
    "ट": "ṭ", "ठ": "ṭh", "ड": "ḍ", "ढ": "ḍh", "ण": "ṇ",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v",
    "श": "ś", "ष": "ṣ", "स": "s", "ह": "h", "ळ": "ḷ",
    "क़": "q", "ख़": "ḵẖ", "ग़": "ġ", "ज़": "z", "ड़": "ṛ", "ढ़": "ṛh", "फ़": "f"
  };
  var IAST_SIGN = {
    "ं": "ṃ", "ः": "ḥ", "ँ": "m̐", "ऽ": "'",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9"
  };
  var VIRAMA = "्";
  var NUKTA = "़";

  function toTelugu(text) {
    var out = "";
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      out += Object.prototype.hasOwnProperty.call(TE, ch) ? TE[ch] : ch;
    }
    return out;
  }

  function toIAST(text) {
    var out = "";
    var i = 0;
    while (i < text.length) {
      var ch = text[i];
      var pair = ch + (text[i + 1] === NUKTA ? NUKTA : "");
      var cons = IAST_CONS[pair] || IAST_CONS[ch];

      if (cons) {
        if (IAST_CONS[pair] && pair.length === 2) i++;   // consumed the nukta
        out += cons;
        var next = text[i + 1];
        if (next === VIRAMA) {
          i += 2;                                        // bare consonant
          continue;
        }
        if (next && Object.prototype.hasOwnProperty.call(IAST_MATRA, next)) {
          out += IAST_MATRA[next];
          i += 2;
          continue;
        }
        out += "a";                                      // inherent vowel
        i += 1;
        continue;
      }

      if (Object.prototype.hasOwnProperty.call(IAST_VOWEL, ch)) { out += IAST_VOWEL[ch]; i++; continue; }
      if (Object.prototype.hasOwnProperty.call(IAST_SIGN, ch)) { out += IAST_SIGN[ch]; i++; continue; }
      if (Object.prototype.hasOwnProperty.call(IAST_MATRA, ch)) { out += IAST_MATRA[ch]; i++; continue; }
      if (ch === VIRAMA || ch === NUKTA) { i++; continue; }

      out += ch;                                          // punctuation, Latin, spaces
      i++;
    }
    return out;
  }

  var CONVERT = { telugu: toTelugu, iast: toIAST };
  var DEVA = /[ऀ-ॿ]/;

  /* Original Devanāgarī of every converted node, so a switch back is exact. */
  var originals = new WeakMap();
  var current = "devanagari";

  function textNodes() {
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        var p = node.parentNode;
        if (!p) return NodeFilter.FILTER_REJECT;
        var tag = p.nodeName;
        if (tag === "SCRIPT" || tag === "STYLE" || tag === "TEXTAREA") return NodeFilter.FILTER_REJECT;
        if (p.closest && p.closest("[data-no-lipi]")) return NodeFilter.FILTER_REJECT;
        var seen = originals.get(node);
        var source = seen === undefined ? node.nodeValue : seen;
        return DEVA.test(source) ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      }
    });
    var list = [];
    var n;
    while ((n = walker.nextNode())) list.push(n);
    return list;
  }

  function apply(script) {
    if (script === current) return;
    var convert = CONVERT[script];
    var nodes = textNodes();
    for (var i = 0; i < nodes.length; i++) {
      var node = nodes[i];
      if (!originals.has(node)) originals.set(node, node.nodeValue);
      var source = originals.get(node);
      node.nodeValue = convert ? convert(source) : source;
    }
    document.documentElement.setAttribute("data-lipi", script);
    current = script;
  }

  global.Lipi = { apply: apply, toTelugu: toTelugu, toIAST: toIAST, get current() { return current; } };
})(window);
