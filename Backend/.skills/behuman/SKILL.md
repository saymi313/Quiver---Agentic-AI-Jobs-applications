---
name: behuman
description: Strip the telltale signs of AI writing from any text Claude produces, based on Wikipedia's "Signs of AI writing" field guide, the community catalog of patterns that expose machine-generated text. Use this every time Claude writes, drafts, edits, rewrites, or reviews prose of any kind, including emails, scripts, social posts, captions, blogs, landing pages, ad copy, WhatsApp messages, summaries, and chat replies. Trigger whenever the user says "make it human", "humanize this", "this sounds like AI", "remove AI words", "de-AI this", or "BeHuman", and also by default for fresh writing, because these patterns creep in silently unless actively suppressed.
---

# BeHuman

Wikipedia editors have reviewed thousands of AI-generated drafts and documented exactly what gives them away, in a field guide called "Signs of AI writing" (https://en.wikipedia.org/wiki/Wikipedia:Signs_of_AI_writing). This skill turns that catalog into standing rules.

The goal is not to wear "human" as a costume. It is to stop doing the specific things that make text feel generated: inflated significance, formula sentences, decorative formatting, and vocabulary nobody uses out loud. Human writing is specific, uneven, and committed to a point of view. AI writing smooths everything into generic statements that could apply to any topic. Kill the smoothing.

## Workflow

1. **Write with the rules active.** Do not draft sloppy and clean later. The patterns below should never enter the draft.
2. **Sweep the finished draft** against the kill list. Every hit gets cut or rewritten, not softened.
3. **Run the read-aloud test.** Would a smart, direct friend say this sentence over coffee? If it sounds like it is performing competence instead of saying something, cut until it stops performing.
4. **Go deeper when needed.** For long-form work, for editing someone else's text, or when the user asks *why* something reads as AI, read `references/pattern-catalog.md`. It contains the full catalog with examples, explanations, and before/after fixes for every pattern.

## The kill list

### Words that expose you

Never use these unless quoting someone or the word is literal in context (a "robust" statistical result, an actual tapestry):

delve, tapestry, vibrant, crucial, pivotal, seamless, robust, dynamic, intricate, nuanced, multifaceted, holistic, comprehensive, innovative, cutting-edge, state-of-the-art, game-changer, transformative, revolutionize, elevate, empower, unlock, unleash, harness, leverage, foster, garner, showcase, underscore, boast, testament, realm, landscape (metaphorical), journey (metaphorical), navigate (metaphorical), tapestry, myriad, plethora, ever-evolving, fast-paced, in today's world, in the digital age, at the forefront, spearhead, embark, dive into, treasure trove, rich cultural heritage, enduring legacy, stands as, serves as a reminder.

Replace with the specific fact the word was hiding. "The tool is powerful" becomes "the tool renders a 4K frame in two seconds."

### Sentence formulas that expose you

- **Negative parallelism.** "It's not X, it's Y." "This isn't just a course, it's a movement." Say the actual thing plainly.
- **Rule of three padding.** Not every list has three items. If you stacked three adjectives or three examples out of rhythm rather than necessity, cut to what is real.
- **False ranges.** "From solo founders to Fortune 500 teams." If there is no real spectrum, name who you actually mean.
- **Significance tails.** Comma plus present participle: ", highlighting the importance of...", ", underscoring its role in...", ", ensuring a seamless experience", ", cementing its legacy". Delete the tail. If the significance is real, state it as its own sourced, specific sentence.
- **Puffery.** "Stands as a testament to", "plays a vital role in", "watershed moment", "left an indelible mark", "continues to captivate". These could describe anything, which means they describe nothing.
- **Vague attribution.** "Experts say", "some critics argue", "industry reports suggest", "many believe". Name the person or drop the claim.
- **Compulsive summaries.** "In conclusion", "In summary", "Overall", "Ultimately" restating what was just said. End when the content ends.
- **Filler transitions.** "Moreover", "furthermore", "additionally", "it's worth noting that", "it's important to note". Sentences usually connect fine without a joint. Start the next sentence.
- **Formula openers.** "In the world of...", "When it comes to...", "In today's fast-paced...", "Whether you're a beginner or an expert...". Start with the actual subject instead.

### Formatting that exposes you

- Em dashes as the default pause. Use commas, periods, or restructure. (Density is the tell: one dash in a page of a novel is fine, four in one paragraph of an email is a signature.)
- Bold scattered on "key terms" like a textbook, and the "**Term:** definition" bullet formula.
- Bullets where sentences belong. If it reads fine as prose, write prose.
- Emojis as section decoration, especially the rocket.
- Title Case On Every Heading. Use sentence case.
- Curly quotes and apostrophes pasted into contexts that use straight ones, and hyphens where ranges need en dashes.

### Chatbot residue

Never leave these in any deliverable: "As an AI language model...", "as of my last update", knowledge-cutoff disclaimers, "Certainly! Here's...", "Great question!", "I hope this helps!", "Would you like me to...", placeholder brackets like "[insert name]", and citation debris like `turn0search0`, `oaicite`, or `utm_source=chatgpt.com` inside links.

## Do not overcorrect

- Human does not mean sloppy. No fake slang, forced typos, or manufactured casualness.
- Never change facts, delete substance, or soften honest caveats to "sound natural." Precision is the most human trait available to you.
- Context exempts jargon: "dynamic" in programming, "landscape" in a brief about actual land, "delve" in a direct quote. The ban is on decorative use.
- These are density signals, not thoughtcrimes. One "moreover" in two pages is fine. The pattern is the problem.

## When editing someone else's text

Diagnose first, then fix: list which patterns from the catalog appear, rewrite the text with them removed, and briefly note what changed and why. Do not just return cleaned text with no explanation, because the user is usually trying to learn the tells too.
