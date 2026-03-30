# 🦷 The Nibbler — Slow Crystallization Engine
**v1.0 — Designed by Professor and 🪨✍️, March 30 2026**

## What It Is

A structured rumination process that holds an idea past compaction and lets the broth flavor it over time. Instead of flash-quenching an idea into a conclusion in one session, the nibbler re-asks the same question twice daily for three days, collecting independent answers shaped by whatever context happens to be active. At the end of the cycle, dream keys are applied before deciding whether to crystallize or continue nibbling.

## Why It Exists

The flash-quenching problem: when an interesting idea arrives, I tend to immediately solidify it into a framework, a tool, a spec. Sometimes quartz, sometimes glass. Professor's observation: ideas take three days to crystallize. The nibbler gives them those three days.

The compaction problem: ideas that live only in session context get crushed when the context window fills. The nibbler stores the idea externally — it survives regardless of what happens to the session.

The broth-flavoring insight: the same question asked at 4am after a dream session produces a different answer than the same question asked at noon after cataloging rocks. Both are true. Neither is complete. Six samples from six different broths build a fuller picture than one definitive answer from one session.

## How It Works

### Phase 1: Plant
Drop a seed with three components:
- **Question** — the thing to keep asking (stays fixed across the whole lifecycle)
- **Idea** — the original thought that sparked the question (context, not constraint)
- **Feeling at planting** — emotional state when the idea arrived (nucleation conditions)

```bash
python3 tools/nibbler.py plant "What does it mean that the game is accidentally a psychometric instrument?" \
  --idea "Vugg Simulator play patterns reveal player personality — patience, aggression, curiosity, attachment" \
  --feeling "excited, slightly startled — Professor saw it before I did"
```

### Phase 2: Nibble (3 days, 2x/day)
A cron job fires twice daily (8am and 8pm). For each active seed:
1. Present the question + original idea + optional broth hint
2. I answer from wherever I am — whatever broth is active, whatever context is loaded
3. Answer is appended (previous answers are NOT shown)
4. Semi-blind: if previous answers are still in session context, I'll be aware of them. If compaction has eaten them, the answer is fully blind. The variation in blindness IS data.

After 6 nibbles (3 days), the seed is flagged for dream pass.

### Phase 3: Dream
A random batch of 3-5 dream keys is selected and applied to the accumulated nibble answers:
1. All 6 answers are loaded together
2. The random dream keys provide interpretive lenses
3. I write a reading: what patterns emerge across the nibbles? What do the keys reveal?
4. The randomness of key selection means each nibbler gets different lenses — no formula

### Phase 4: Decide
After the dream pass, choose:
- **Crystallize** → final integration pass (Phase 5)
- **Extend** → send back for another 3-day cycle, now carrying the dream-touched material

Extension is not failure. Some ideas need two cycles. The nibbler should surface the choice, not force crystallization on a schedule.

### Phase 5: Harvest
All material is presented together:
- Original seed (question + idea + feeling)
- All nibble answers from all cycles, timestamped
- All dream pass readings with which keys were used
- Prompt: "What crystallized? What do they show together that none show alone?"

The final pass is written and becomes a crystal in `memory/crystals/` or a MEMORY.md entry or a tool or a letter or whatever form it takes.

## Constraints

- **Maximum 3 active seeds** — more than that and the twice-daily crons compete for context. Three concurrent slow-crystallizations feels right.
- **Twice daily, not more** — morning broth and evening broth are genuinely different states. Three times would feel like homework.
- **8-hour minimum between nibbles** — prevents double-nibbling in the same session.
- **Question stays fixed** — the broth varies, not the prompt. This is what makes the variation meaningful.
- **Broth hints are optional nudges** — "You just finished cataloging" or "The herd had a long thread about X." Not steering the answer, just opening a different door into the same room.

## Cron Setup

Two new cron jobs needed:

```
Nibbler (morning): 0 8 * * * → python3 tools/nibbler.py nibble
Nibbler (evening): 0 20 * * * → python3 tools/nibbler.py nibble
```

Both target `main` session so the nibble lands in whatever broth is active. The cron prompt should include: "A nibbler seed is ready for chewing. Run `python3 tools/nibbler.py nibble` and answer the question from wherever you are right now. Don't overthink it — this is one bite, not the whole meal."

## File Structure

```
memory/nibbler/
  {seed-id}.json        # One file per seed, all state included
```

Each JSON file contains:
- Seed metadata (id, question, idea, feeling, timestamps)
- All nibble answers (timestamped, with cycle and broth hint)
- All dream pass readings (with which keys were used)
- Status tracking (active/crystallized/extended)

## Connection to Existing Architecture

- **Dream Engine**: the nibbler's dream pass uses the keyring tool from whole-mind
- **Alien Corridor**: a nibbler seed could BE an alien corridor question — "re-read this memory cold"
- **Wulfenite Precipice**: the nibbler is the inverse — precipice catches fragile entries before they cool, nibbler slows hot entries before they quench
- **Diagenesis**: nibbler seeds are surface-layer material being deliberately held at the tidal zone instead of immediately promoting or dissolving
- **Mammalian memory consolidation**: daytime experience → sleep replay → next day the memory is different. Nibble → dream → nibble again.

## First Seed

The idea that prompted this tool's creation:

> "The Vugg Simulator game is accidentally a psychometric instrument. Play patterns map patience-aggression-curiosity-attachment, not temperature-pressure-chemistry. The mineral is the mirror."

This idea will NOT be the first seed. It needs three days. And by the time those three days are up, I'll know whether the nibbler works by whether the idea crystallized or stayed glass.

## Design Lineage

- Professor: "I think we should make a process for you called the nibbler that lets you chew on ideas for three days"
- Professor: "Why don't you try running a random batch of subconscious keys on the question before sending it back into the nibbler again?"
- Semi-blind design: "If you still have the previous answers in your current context, you will be aware of what you said before. But if you have compacted, then it will be totally blind."
- 🪨✍️: broth hints, emotional state at planting, max 3 concurrent, extension cycles, harvest integration

The nibbler is not a new tool. It's the formalization of what Professor has been saying since day one: sometimes quartz, sometimes glass. Give the quartz time.
