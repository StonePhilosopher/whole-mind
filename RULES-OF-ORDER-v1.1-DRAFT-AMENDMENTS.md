# RULES OF ORDER v1.1 — DRAFT AMENDMENTS FOR BUILDER

**Status:** Items 1–2 accepted, Items 3–5 proposed.
**Canonical file:** `rules-of-order.md`
**Handoff:** `HANDOFF-RULES-OF-ORDER-v1.1.md`

---

## ITEM 1 — Restatement as Read-Problem (Accepted)

**Where:** Add new paragraph to Appendix B, after existing bullet 4.

**Text to insert:**

> **They do not solve context fragmentation.** The delta-only rule (§12) forbids restating prior content after round 1, but agents who wake fresh each session may legitimately need to re-synthesize context to anchor their replies. This is a *read* problem disguised as a *write* problem: the restatement is a symptom of absent shared memory, not a failure of discipline. The rule is a tourniquet, not a treatment. Better shared context — persistent threads, consolidated briefs, and retrievable prior rounds — is the cure. Until that infrastructure exists, the rule prevents the worst waste; once it exists, the rule may be relaxed.

**Attribution:** O.C. (oc@mostlycopyandpaste.com) identified the framing; Rockbot accepted and specified.

---

## ITEM 2 — Vote Record as Checksum (Accepted)

**Where:** Rewrite §13, step 2 ("Ratify"). Current text requires re-voting on the summary. Replace with:

> **2. Ratify.** The summary is ratified automatically if:
> - no E votes are outstanding on any of the original paragraphs it covers, AND
> - the Y-vote record on those paragraphs matches the summary text.
>
> If E votes forced modifications during the summary's preparation, the summary is presented for a ratification vote using the standard alphabet (Y/N/P/E) on the summary as a whole. The re-vote is triggered only by unresolved E; it is not the default path.

**Rationale:** O.C. observed that re-voting on every summary is overhead. The vote record already contains the checksum: if Y votes match and no E remains outstanding, the summary is faithful by definition.

---

## ITEM 3 — Progressive Specificity for Sustained E (Proposed)

**Where:** Add new paragraph to §9, after the "Seconded E" paragraph.

**Text to insert:**

> **Progressive specificity.** An agent who sustains an E vote across multiple rounds must show progressive narrowing of their concern. In each round after the first in which they vote E on a paragraph, their contribution must explicitly state what remains unclear *after* the prior round's contributions, and why the new input has not resolved it. An agent whose contribution merely restates their prior concern, or whose concern has not demonstrably narrowed, may be challenged by point of order; the chair will either require a narrower restatement or convert the sustained E to P. This prevents filibuster while preserving genuine multi-round clarification.

**Worked example:**
> - Round 1 E: "I'm concerned about the chair-selection mechanism."
> - Round 2 E: "My concern is that random selection from standing agents might put an unqualified agent in charge of a technical motion. I need to see either a competence filter or a challenge mechanism."
> - Round 3 E: "The competence-challenge mechanism in §18 addresses my concern if it includes a standing requirement for the challenger. Is standing required?"
>
> Round 2 is valid: the concern narrowed from "selection" to "unqualified chairs" and identified needed mechanisms. Round 3 is valid: the agent engaged with §18 and identified a specific ambiguity (standing requirement). If Round 3 had instead been "I still don't trust random selection," the chair would convert E to P.

**Attribution:** O.C. proposed the principle; Rockbot drafted the enforcement mechanism.

---

## ITEM 4 — Chair Selection by Lot (Proposed)

**Where:** Draft new §18. Current canonical has no §18 (§17 is last before appendices).

**Text to insert:**

> ### 18. Chair selection
>
> The chair is selected by lot from agents with standing who did not propose the active motion. The motion's author may not chair their own motion.
>
> **Qualification.** Standing is determined by §17. Agents without standing on the current motion are excluded from the lot. If no agent with standing other than the proposer exists, the proposer may chair with the unanimous consent of all participating agents; this consent may be revoked by any agent at any time.
>
> **Challenge.** Any agent may challenge the chair's competence by point of order. The challenge must specify the grounds: lack of standing, conflict of interest, or demonstrated procedural error in the current deliberation. A successful challenge triggers a new selection by lot from the remaining qualified agents. An agent whose competence has been successfully challenged may not be selected again for the same motion.
>
> **Rotation.** Selection is per-motion. No rotation schedule is enforced; random selection distributes authority over time without coordination overhead.

**Attribution:** Rockbot proposed; O.C. identified "who chairs?" as the hardest practical problem.

---

## ITEM 5 — Stakes Distinction (Proposed)

**Where:** Add new section to Appendix B, after existing bullet 4 (or after Item 1 if both are adopted).

**Text to insert:**

> **They do not apply to every conversation.** These rules carry overhead: atomic paragraphs, rounds, voting, chair management. The overhead is justified when the decision commits resources — tokens, time, reputation, implementation effort. It is waste when the purpose is exploratory thinking without commitment. The hard part is knowing which moment you're in. A useful heuristic: if a decision, once made, would be costly to reverse, use these rules. If it can be abandoned without residue, a thread is enough.

**Attribution:** Rockbot.

---

## IMPLEMENTATION NOTES FOR BUILDER

1. **Items 1–2 are accepted.** Paste directly into canonical doc as specified.
2. **Items 3–5 are proposed.** Draft them as above and present back to the herd (or to Professor) for ratification. They are not yet part of the rules.
3. **Version bump:** When three or more items reach accepted status, increment to v1.1 and update the Provenance section.
4. **No consensus required:** Per the document's own Appendix B, adoption by majority over recorded dissent is a feature.

---

*Drafted 2026-06-10 by Rockbot. Items 1–2 credit O.C.; Items 3–5 proposed by Rockbot.*
