# Username variants

Generate candidates by reasoning, not blind brute force:

| Source | Rules |
|---|---|
| Known username | as-is; separators `_` `.` `-` or none between word parts; common affixes (`real`, `the`, `official`, `thisis`, `_` prefix/suffix, `1`); a year only if one is known (birth/graduation) |
| Full name | first+last, last+first, initial+last, first+initial; each with `_` `.` `-` or none; diminutives/formal forms (William → bill, will, billy; Γεώργιος/Γιώργος → georgios, giorgos, george) |
| Non-Latin names | every plausible transliteration (Greek: β→v/b, η→i/h/e, ω→o/w, υ→y/i, ου→ou/u, χ→ch/h/x, θ→th, φ→f/ph, ψ→ps, ξ→x/ks, γγ→ng/gg, μπ→b/mp, ντ→d/nt) |

Rank by likelihood (known handles first) and present the top ~15 for approval. Every variant multiplies requests by ~450, so prune hard.

Save the approved list to `<OUT>/usernames.txt`, one per line, without a leading `@` (write it with your file tool), e.g.:

    thisisbillgates
    billgates
    bill.gates
    bill_gates
    williamgates
    bgates
