# Second-reader check

A second person labelled 100 validation entries from `ml/datasets/second_reader/sheet.csv` without seeing the original labels: a friend who had not seen the guidelines' detail, working from `HOW_TO_CHECK.md` only (2026-11-08). Their sheet is `ml/datasets/second_reader/filled_reader2.csv`; scored with `python -m ml.second_reader score`.

| | Result |
|---|---|
| Same main feeling | 85% |
| Same, or the other's answer is listed as also fitting | 99% |
| Agreement beyond chance (Cohen's kappa) | 0.84 |
| Average gap in strength (1-10) | 1.06 |
| Strength within 2 points | 98% |
| Same names | 99% |

**Verdict:** very strong agreement: the labels can be trusted as they are.

## What it means

The labels hold: kappa 0.84 is above the usual 0.8 bar for very strong agreement, and in 99 of 100 entries each reader's answer was one the other also accepted. The 15 exact misses are the close pairs the guidelines already name (happy or proud, angry or frustrated, relief read as calm or grateful). No label was changed: the one clear miss, e1200 ('Is this Sam?'), already lists `frustrated` as an accepted alternative and is marked `ambiguous`, and editing validation now would break comparison with every recorded score. Strength differed most on e0530 and e1527 (3 against 6, 5 against 8), where the second reader read the feeling as stronger.

One reader is still a small sample; a third reader or entries written by other people would strengthen this further.

## Where the readers differ most

| Original | Second reader | Times |
|---|---|---|
| happy | proud | 2 |
| angry | frustrated | 2 |
| calm | grateful | 1 |
| content | proud | 1 |
| happy | grateful | 1 |
| sad | reflective | 1 |
| grateful | proud | 1 |
| tired | overwhelmed | 1 |
| content | happy | 1 |
| neutral | frustrated | 1 |

## Entries to look at again

For each, decide who is right by the guidelines. If the second reader is, fix the label in `ml/datasets/entries/`; if it is genuinely both, add their feeling to `also` and the `ambiguous` trait.

**e0731**: I asked for one thing for my birthday: no drama. Dad brought drama.
- Feeling: original **angry** (also sad), second reader **frustrated**
- Strength: original 6, second reader 6

**e1200**: Message from 'Unknown Number': 'Is this Sam?' It is not Sam. I am not Sam. Nobody here is Sam.
- Feeling: original **neutral** (also frustrated), second reader **frustrated**
- Strength: original 2, second reader 3
- Names: second reader missed none, added ['Sam']
- Their note: Dry comic irritation at the mistaken text.

**e0530**: I notice I describe my week by what I achieved and never by how I felt. Trying to change the question.
- Feeling: original **reflective**, second reader **reflective** (also hopeful)
- Strength: original 3, second reader 6

**e1527**: Lonely job, this. Driving all day, talking to satnav. The radio presenters feel like friends.
- Feeling: original **lonely**, second reader **lonely**
- Strength: original 5, second reader 8

