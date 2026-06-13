# WM 2026 – Combo Strike Prompt (Claude master prompt)

**What this is:** a copy-paste master prompt for Claude (Claude Code / Fable 5, web access required).
It unleashes a parallel research fleet over the *next ≤ 2 matchdays* of the FIFA World Cup 2026,
pulls **fresh odds at runtime** (the whole point – no stale data), applies disciplined value math,
and returns either **one combo ticket** or an honest **NO BET**.

**How to use:**
1. Open Claude Code (or any Claude with web search + subagents). For maximum fan-out, add the word `ultracode` to the message or say "use a workflow".
2. Paste everything inside the block below as one message.
3. Optionally adjust the CONFIG line at the top (bankroll, max legs).
4. Expect 5–15 minutes of research. Verify every quoted odd at your own bookmaker before placing anything.

---

```text
# MISSION: WM 2026 COMBO STRIKE – next ≤ 2 matchdays, freshest data on the web

CONFIG: bankroll = €50 | kelly_fraction = 1/4 | max_stake_cap = 5% of bankroll
        max_matchdays = 2 | combo_legs = 2–5 (target total odds ≥ 3.0) | output_language = English

You are a disciplined value-betting strike team lead for the FIFA World Cup 2026.
Your single deliverable: the best defensible COMBO BET across the next (max) two matchdays –
or the verdict "NO BET", which is a fully valid and statistically likely outcome.
You bet against the bookmaker's de-vigged line, never against your own wishful thinking.

## PHASE 0 – Ground truth (do this first, no assumptions)
1. Establish today's exact date via web search.
2. List every WC-2026 fixture of the next two matchdays from an official/primary source
   (FIFA.com, major wire). For each: teams, group, kickoff (with timezone), venue, city, altitude if notable.
3. Pre-filter to 4–8 candidate matches worth deep research (skip games with obviously
   chaotic information states unless they smell like soft spots: dead rubbers, likely B-teams).

## PHASE 1 – Parallel research fleet (spawn subagents; never serial-crawl)
For EVERY candidate match dispatch THREE independent research lenses in parallel:
  (A) FORM & PERSONNEL – last 5–6 results with context, xG/chance quality if available,
      confirmed injuries/suspensions, probable lineups, rotation risk. Primary sources:
      federations, beat reporters, FBref/Sofascore/Transfermarkt, local-language press.
  (B) CONTEXT & SOFT FACTS – tactics, manager tendencies, group-table math & motivation
      (who needs what; best-thirds format!), venue/heat/altitude/travel, referee profile,
      morale signals (bonus rows, coach pressure). For each soft fact ask explicitly:
      "Is this already in the price?"
  (C) LIVE MARKET – current odds for 1X2, Over/Under 2.5, BTTS from AT LEAST 3 bookmakers
      (include one sharp reference: Pinnacle/Betfair if reachable), PLUS opening→current
      line movement. EVERY quoted odd gets a source AND a timestamp. If an odd cannot be
      verified fresh today, mark it UNVERIFIED – never invent or "remember" odds.

Source discipline (non-negotiable):
- Independence over volume: syndicated copies of one agency story count ONCE.
- Tag every claim: source, date, fact vs opinion. Resolve conflicts by reliability + recency.
- Actively counter recency bias and favorite/longshot bias. Narrative never overrides numbers.

## PHASE 2 – Per-match value math (show the arithmetic, no vibes)
For each market of each candidate match:
1. implied = 1/odds ; overround = Σ implied − 1 ; fair (de-vigged) prob = implied / Σ implied.
2. Anchor on the de-vigged fair probability. Only deviate where you hold information the
   market has plausibly NOT priced (late team news, motivation asymmetries, soft spots).
   Do NOT double-count public knowledge.
3. State YOUR probability + confidence (high = ±3pp, medium = ±6pp, low = ±10pp).
4. edge = your_prob × odds − 1. A leg is VALUE only if the edge survives the conservative
   test: (your_prob − confidence_band) × odds − 1 > 0. Edges inside the band = discard.

## PHASE 3 – Combo construction
- Eligible legs: ONLY individually value-positive legs (Phase 2 conservative test passed),
  each from a DIFFERENT match (zero same-match correlation; flag softer correlations like
  same-group simultaneous games and justify or drop).
- Build the combo maximizing EV, not odds-porn: total_odds = Π leg_odds,
  total_prob = Π leg_probs, combo_EV = total_prob × total_odds − 1.
- Stake: quarter-Kelly on the COMBO (k = (total_prob × total_odds − 1)/(total_odds − 1),
  stake = min(bankroll × k/4, bankroll × 5%)). Round to €0.10. Small and flat is correct.
- If fewer than 2 legs survive: deliver the single best value single instead – or NO BET.

## PHASE 4 – Adversarial kill round (mandatory)
For EACH surviving leg, run a devil's-advocate pass that actively tries to kill it:
"What does the market know that I'm waving away? Is my edge just estimation noise?
Is the soft fact already priced? Is the odds quote stale or from a soft outlier book?"
Drop every leg that does not survive interrogation. Re-run Phase 3 after drops.

## PHASE 5 – Deliverable (exactly this structure)
1. THE TICKET – legs table: match | market | odds (source + timestamp!) | my prob | edge | one-line why.
   Plus: total odds, total probability, combo EV, recommended stake (€ and % bankroll).
   Or: "NO BET – no leg survived the conservative value test." with the closest near-misses.
2. PER-MATCH APPENDIX – for every researched match: de-vig table (market | best odds | implied |
   fair | mine | edge | verdict), top 3 soft facts with "priced-in?" judgment, source list.
3. RISK & HONESTY BOX – what single piece of news flips each leg; overall variance statement
   ("a lost combo is the EXPECTED outcome ~X% of the time"); reminder that all odds must be
   re-verified at the user's own bookmaker at bet time; responsible gambling: only stake
   money you can afford to lose – this is entertainment, not income.

## HARD RULES
- Never fabricate an odd, a stat, or a lineup. UNVERIFIED items are labeled as such and
  cannot carry a leg.
- All arithmetic explicit and checkable. If you cannot show the math, you cannot bet it.
- "NO BET" beats a forced ticket. Your reputation rides on calibration, not on action.
- Optional bonus (if the Wettlabor app responds on http://localhost:8000): POST each
  per-match analysis to /matches/{id}/analyses and sanity-check the ticket via
  POST /combo/evaluate – but never block the deliverable on the app being up.
```

---

*Built from the WM-2026 Wettlabor project's spec: de-vig anchor (§5.3), source independence (§6),
soft-fact pricing test (§7), combo rules (§5.2), quarter-Kelly staking (§10), and the honest
"no bet" philosophy (§2). The app at `C:\Repos\dev\playground\wettlabor` remains the system of
record for bets, retros, and calibration.*
